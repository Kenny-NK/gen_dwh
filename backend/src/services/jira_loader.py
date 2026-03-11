"""Native Jira PAT extractor for direct PostgreSQL loads."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import asyncpg
from sqlalchemy.engine import make_url

from src.core.config import settings
from src.core.db_utils import quote_ident
from src.schemas.jira import JiraExtractionConfig
from src.services.jira_issue_normalization import normalize_issue_record
from src.services.jira_service import JiraService
from src.services.record_flattening import (
    flatten_record,
    normalize_identifier,
    stringify_flat_value,
)

_META_COLUMNS = ["_record_id", "_cursor_value", "_loaded_at", "_raw"]


@dataclass
class JiraLoadResult:
    success: bool
    records_processed: int = 0
    source_records_total: int | None = None
    tables_processed: int = 0
    error_message: str | None = None
    state_file: str | None = None
    last_cursor_values: dict[str, str] = field(default_factory=dict)


def _target_connection_kwargs() -> dict[str, object]:
    url = make_url(settings.database_business_url)
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username or "gendwh",
        "password": url.password or "",
        "database": url.database or "gendwh_business",
    }


def _normalize_record_columns(record: dict[str, Any]) -> tuple[dict[str, str | None], str | None]:
    normalized = {
        key: value
        for key, value in flatten_record(record).items()
        if key not in _META_COLUMNS
    }

    record_id = (
        normalized.get("id")
        or normalized.get("accountid")
        or normalized.get("key")
        or normalized.get("name")
    )
    return normalized, record_id


def _cursor_value(record: dict[str, Any], replication_key: str | None) -> str | None:
    if not replication_key:
        return None
    raw = record.get(replication_key)
    if raw is None:
        return None
    return stringify_flat_value(raw)


async def _ensure_table_shape(
    conn: asyncpg.Connection,
    schema_name: str,
    table_name: str,
    columns: list[str],
    upsert_column: str | None,
) -> None:
    schema_sql = quote_ident(schema_name)
    table_sql = quote_ident(table_name)
    await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_sql}")

    existing_rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """,
        schema_name,
        table_name,
    )
    existing_columns = {str(row["column_name"]) for row in existing_rows}

    if not existing_columns:
        base_columns = [
            '"_record_id" TEXT',
            '"_cursor_value" TEXT',
            '"_loaded_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()',
            '"_raw" JSONB NOT NULL',
        ]
        dynamic_columns = [f"{quote_ident(column)} TEXT" for column in columns]
        await conn.execute(
            f"CREATE TABLE IF NOT EXISTS {schema_sql}.{table_sql} "
            f"({', '.join(base_columns + dynamic_columns)})"
        )
        existing_columns = set(columns) | set(_META_COLUMNS)
    else:
        for column in columns:
            if column in existing_columns:
                continue
            await conn.execute(
                f"ALTER TABLE {schema_sql}.{table_sql} ADD COLUMN {quote_ident(column)} TEXT"
            )

    if upsert_column:
        index_name = normalize_identifier(f"uq_{table_name}_{upsert_column}", "uq_upsert")
        await conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {quote_ident(index_name)} "
            f"ON {schema_sql}.{table_sql} ({quote_ident(upsert_column)})"
        )


async def _insert_rows(
    conn: asyncpg.Connection,
    schema_name: str,
    table_name: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    write_mode: str,
    upsert_column: str | None,
    on_progress: Callable[[int], Awaitable[None]] | None = None,
) -> int:
    schema_sql = quote_ident(schema_name)
    table_sql = quote_ident(table_name)

    if write_mode == "replace":
        await conn.execute(f"TRUNCATE TABLE {schema_sql}.{table_sql}")

    if not rows:
        return 0

    insert_columns = ["_record_id", "_cursor_value", "_raw", *columns]
    columns_sql = ", ".join(quote_ident(column) for column in insert_columns)
    placeholders_sql = ", ".join(f"${index}" for index in range(1, len(insert_columns) + 1))
    insert_prefix = (
        f"INSERT INTO {schema_sql}.{table_sql} ({columns_sql}) VALUES ({placeholders_sql})"
    )

    if write_mode == "upsert" and upsert_column:
        update_columns = [column for column in insert_columns if column != upsert_column]
        set_sql = ", ".join(
            f"{quote_ident(column)} = EXCLUDED.{quote_ident(column)}"
            for column in update_columns
        )
        statement = (
            f"{insert_prefix} ON CONFLICT ({quote_ident(upsert_column)}) DO UPDATE SET {set_sql}"
        )
    else:
        statement = insert_prefix

    inserted_total = 0
    batch_size = 200
    for offset in range(0, len(rows), batch_size):
        chunk_rows: list[tuple[Any, ...]] = []
        for row in rows[offset : offset + batch_size]:
            chunk_rows.append(
                (
                    row["_record_id"],
                    row["_cursor_value"],
                    json.dumps(row["_raw"], ensure_ascii=False),
                    *[row.get(column) for column in columns],
                )
            )
        await conn.executemany(statement, chunk_rows)
        inserted_total += len(chunk_rows)
        if on_progress:
            await on_progress(inserted_total)
    return inserted_total


def _resolve_upsert_column(
    table_spec: dict[str, Any],
    stream_name: str,
    columns: list[str],
    global_upsert_key: str | None,
) -> str | None:
    stream_meta = JiraService.STREAMS.get(stream_name)
    primary_keys = list(stream_meta.primary_keys) if stream_meta else []
    candidate_keys = [
        str(global_upsert_key or "").strip(),
        *primary_keys,
        str(table_spec.get("replication_key") or "").strip(),
        "issue_id",
        "issue_key",
        "id",
        "accountId",
        "key",
    ]
    normalized_columns = set(columns) | {"_record_id", "_cursor_value", "_raw"}
    for candidate in candidate_keys:
        if not candidate:
            continue
        normalized = normalize_identifier(candidate, candidate.lower())
        if normalized in normalized_columns:
            return normalized
    return "_record_id" if "_record_id" in normalized_columns else None


def _prepare_rows(
    records: list[dict[str, Any]],
    replication_key: str | None,
) -> tuple[list[str], list[dict[str, Any]], str | None]:
    all_columns: list[str] = []
    seen_columns: set[str] = set()
    prepared_rows: list[dict[str, Any]] = []
    max_cursor: str | None = None

    for record in records:
        normalized_columns, record_id = _normalize_record_columns(record)
        for column in normalized_columns:
            if column in seen_columns:
                continue
            seen_columns.add(column)
            all_columns.append(column)
        cursor = _cursor_value(record, replication_key)
        if cursor and (max_cursor is None or cursor > max_cursor):
            max_cursor = cursor
        prepared_rows.append(
            {
                **normalized_columns,
                "_record_id": record_id,
                "_cursor_value": cursor,
                "_raw": record,
            }
        )

    return all_columns, prepared_rows, max_cursor


def _prepare_issue_rows(
    records: list[dict[str, Any]],
    replication_key: str | None,
) -> tuple[list[str], list[dict[str, Any]], str | None]:
    all_columns: list[str] = []
    seen_columns: set[str] = set()
    prepared_rows: list[dict[str, Any]] = []
    max_cursor: str | None = None

    for record in records:
        normalized_columns = normalize_issue_record(record)
        for column in normalized_columns:
            if column in seen_columns:
                continue
            seen_columns.add(column)
            all_columns.append(column)
        raw_fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        cursor = _cursor_value(raw_fields, replication_key)
        if cursor and (max_cursor is None or cursor > max_cursor):
            max_cursor = cursor
        prepared_rows.append(
            {
                **normalized_columns,
                "_record_id": normalized_columns.get("issue_id") or normalized_columns.get("issue_key"),
                "_cursor_value": cursor,
                "_raw": record,
            }
        )

    return all_columns, prepared_rows, max_cursor


async def _store_stream_records(
    conn: asyncpg.Connection,
    target_schema: str,
    target_table: str,
    table_spec: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    write_mode: str,
    global_upsert_key: str | None,
    progress_callback: Callable[[int], Awaitable[None]] | None = None,
) -> tuple[int, str | None]:
    replication_key = str(table_spec.get("replication_key") or "").strip() or None
    stream_name = str(table_spec.get("stream") or table_spec.get("table") or "").strip().lower()
    if stream_name == "issues":
        columns, rows, max_cursor = _prepare_issue_rows(records, replication_key)
    else:
        columns, rows, max_cursor = _prepare_rows(records, replication_key)
    upsert_column = None
    if write_mode == "upsert":
        upsert_column = _resolve_upsert_column(
            table_spec,
            stream_name,
            columns,
            global_upsert_key,
        )
        if not upsert_column:
            raise ValueError(
                f"Не удалось определить upsert key для Jira stream '{table_spec.get('stream')}'."
            )
    await _ensure_table_shape(conn, target_schema, target_table, columns, upsert_column)
    inserted = await _insert_rows(
        conn,
        target_schema,
        target_table,
        columns,
        rows,
        write_mode,
        upsert_column,
        on_progress=progress_callback,
    )
    return inserted, max_cursor


async def run_jira_pat_to_postgres(
    source_config: dict,
    target_config: dict,
    tables: list[dict] | None = None,
    progress_callback: Callable[[int, int | None], Awaitable[None]] | None = None,
) -> JiraLoadResult:
    table_specs = tables or []
    if not table_specs:
        return JiraLoadResult(success=False, error_message="Для потока не выбраны Jira streams")

    extraction = JiraExtractionConfig.model_validate(source_config.get("extraction_config") or {})
    if extraction.auth_type != "pat_bearer":
        return JiraLoadResult(success=False, error_message="Native Jira extractor supports only PAT auth")

    target_schema = normalize_identifier(str(target_config.get("schema") or "public"), "public")
    write_mode = str(target_config.get("write_mode") or "append").lower()
    if write_mode not in {"append", "replace", "upsert"}:
        return JiraLoadResult(success=False, error_message=f"Неподдерживаемый режим записи: {write_mode}")

    global_upsert_key = str(target_config.get("upsert_key") or "").strip() or None
    records_processed = 0
    tables_processed = 0
    last_cursor_values: dict[str, str] = {}

    async with JiraService(
        str(source_config.get("host") or ""),
        str(source_config.get("username") or ""),
        str(source_config.get("password") or ""),
        auth_type="pat_bearer",
    ) as jira:
        try:
            stream_payloads = await jira.extract_records(
                streams=[
                    str(item.get("stream") or item.get("table") or "").strip()
                    for item in table_specs
                    if str(item.get("stream") or item.get("table") or "").strip()
                ],
                project_keys=extraction.project_keys,
                jql=extraction.jql,
                query_mode=extraction.query_mode,
                batch_size=extraction.batch_size,
                start_date=extraction.start_date,
                incremental_enabled=extraction.incremental_enabled,
                cursors_by_stream={
                    str(item.get("stream") or item.get("table") or "").strip().lower():
                    str(item.get("last_cursor_value") or "").strip() or None
                    for item in table_specs
                },
            )
        except Exception as exc:
            classified = JiraService.classify_error(exc)
            return JiraLoadResult(success=False, error_message=classified.message)

    conn = await asyncpg.connect(**_target_connection_kwargs())
    try:
        for table_spec in table_specs:
            stream_name = str(table_spec.get("stream") or table_spec.get("table") or "").strip().lower()
            if not stream_name:
                continue
            target_table = normalize_identifier(
                str(table_spec.get("table_name") or table_spec.get("table") or stream_name),
                stream_name,
            )
            stream_records = stream_payloads.get(stream_name) or []

            async def _stream_progress(delta: int) -> None:
                if progress_callback:
                    await progress_callback(records_processed + delta, None)

            inserted, max_cursor = await _store_stream_records(
                conn,
                target_schema,
                target_table,
                table_spec,
                stream_records,
                write_mode=write_mode,
                global_upsert_key=global_upsert_key,
                progress_callback=_stream_progress,
            )
            records_processed += inserted
            tables_processed += 1
            if max_cursor:
                last_cursor_values[stream_name] = max_cursor
            if progress_callback:
                await progress_callback(records_processed, None)
    finally:
        await conn.close()

    return JiraLoadResult(
        success=True,
        records_processed=records_processed,
        source_records_total=records_processed,
        tables_processed=tables_processed,
        last_cursor_values=last_cursor_values,
    )
