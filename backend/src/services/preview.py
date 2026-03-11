"""Preview execution service (T056, T057)."""

import asyncio
from datetime import UTC, datetime, timedelta
import re
from uuid import UUID

import asyncpg
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.db_utils import quote_ident
from src.models.flow import Flow
from src.models.flow_table import FlowTable
from src.models.preview_session import PreviewSession
from src.models.source import Source
from src.schemas.jira import JiraExtractionConfig
from src.services.connection import build_s3_endpoint_url, decrypt_password
from src.services.jira_service import JiraService
from src.services.record_flattening import flatten_record
from src.services.s3_loader import parse_s3_object_rows

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_PREVIEW_MODES = {"auto", "live", "snapshot"}


def _validate_identifier(value: str, field: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value


class PreviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_preview_mode(value: str | None, *, fallback: str = "auto") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in _PREVIEW_MODES:
            return normalized
        return fallback

    @classmethod
    def _supported_preview_modes_for_source(cls, source_type: str | None) -> set[str]:
        normalized = str(source_type or "").strip().lower()
        if normalized in {"postgres", "s3", "jira"}:
            return {"live", "snapshot"}
        return {"snapshot"}

    @classmethod
    def _auto_preview_mode_for_source(cls, source_type: str | None) -> str:
        normalized = str(source_type or "").strip().lower()
        if normalized == "postgres":
            return "live"
        return "snapshot"

    @classmethod
    def _resolve_preview_mode(
        cls,
        flow: Flow,
        *,
        requested_mode: str | None = None,
    ) -> tuple[str | None, str]:
        normalized_request = cls._normalize_preview_mode(requested_mode, fallback="")
        requested = normalized_request or None
        if requested is not None and not settings.preview_allow_mode_override:
            requested = None

        base_mode = requested or cls._normalize_preview_mode(
            getattr(flow, "preview_mode", None),
            fallback=settings.preview_default_mode,
        )
        supported_modes = cls._supported_preview_modes_for_source(getattr(flow.source, "source_type", None))
        resolved = base_mode
        if resolved == "auto":
            resolved = cls._auto_preview_mode_for_source(getattr(flow.source, "source_type", None))
        if resolved not in supported_modes:
            resolved = "snapshot" if "snapshot" in supported_modes else next(iter(sorted(supported_modes)))
        return requested, resolved

    @staticmethod
    def _ttl_for_mode(mode: str) -> timedelta:
        if mode == "snapshot":
            return timedelta(minutes=settings.preview_snapshot_ttl_minutes)
        return timedelta(minutes=settings.preview_live_ttl_minutes)

    async def _load_flow_for_preview(self, flow_id: UUID) -> Flow | None:
        result = await self.session.execute(
            select(Flow)
            .options(
                selectinload(Flow.tables),
                selectinload(Flow.source).selectinload(Source.credential),
            )
            .where(Flow.id == flow_id)
        )
        return result.scalar_one_or_none()

    async def _mark_expired(self, preview: PreviewSession) -> None:
        if preview.status != "expired":
            preview.status = "expired"
            preview.completed_at = preview.completed_at or datetime.now(UTC)
            await self.session.commit()

    async def _ensure_session_available(self, preview: PreviewSession | None) -> PreviewSession | None:
        if preview is None:
            return None
        if preview.expires_at is not None and preview.expires_at <= datetime.now(UTC):
            await self._mark_expired(preview)
            return preview
        return preview

    async def create_session(
        self,
        flow_id: UUID,
        row_limit: int = 100,
        tables_available: list[str] | None = None,
        requested_mode: str | None = None,
    ) -> PreviewSession:
        """Create a new preview session."""
        flow = await self._load_flow_for_preview(flow_id)
        if flow is None or flow.source is None or flow.source.credential is None:
            raise ValueError("Flow preview configuration is incomplete")

        normalized_limit = min(row_limit, 10000)
        requested, resolved = self._resolve_preview_mode(flow, requested_mode=requested_mode)
        now = datetime.now(UTC)
        preview = PreviewSession(
            flow_id=flow_id,
            row_limit=normalized_limit,
            status="pending",
            tables_available=tables_available,
            requested_mode=requested,
            resolved_mode=resolved,
            expires_at=now + self._ttl_for_mode(resolved),
        )
        self.session.add(preview)
        await self.session.flush()

        try:
            if resolved == "snapshot":
                snapshot_payload: dict[str, dict] = {}
                total_rows = 0
                selected_tables = tables_available or [
                    f"{flow_table.source_schema}.{flow_table.source_table}"
                    for flow_table in flow.tables
                ]
                for table_name in selected_tables:
                    flow_table = self._resolve_flow_table(flow, table_name)
                    data = await self._fetch_live_preview_data(
                        flow=flow,
                        flow_table=flow_table,
                        row_limit=normalized_limit,
                        page=1,
                        page_size=normalized_limit,
                        sort_by=None,
                        sort_order="asc",
                    )
                    snapshot_payload[f"{flow_table.source_schema}.{flow_table.source_table}"] = {
                        "columns": data.get("columns", []),
                        "rows": data.get("rows", []),
                        "total": int(data.get("total") or 0),
                    }
                    total_rows += int(data.get("total") or 0)
                preview.snapshot_payload = snapshot_payload
                preview.total_rows = total_rows

            preview.status = "completed"
            preview.completed_at = now
        except Exception as exc:
            preview.status = "failed"
            preview.error_message = str(exc)[:2000]
            preview.completed_at = datetime.now(UTC)

        await self.session.commit()
        return preview

    async def get_session(self, session_id: UUID) -> PreviewSession | None:
        result = await self.session.execute(
            select(PreviewSession).where(PreviewSession.id == session_id)
        )
        preview = result.scalar_one_or_none()
        return await self._ensure_session_available(preview)

    async def get_session_for_flow(self, session_id: UUID, flow_id: UUID) -> PreviewSession | None:
        result = await self.session.execute(
            select(PreviewSession).where(
                PreviewSession.id == session_id,
                PreviewSession.flow_id == flow_id,
            )
        )
        preview = result.scalar_one_or_none()
        return await self._ensure_session_available(preview)

    async def update_status(
        self, session_id: UUID, status: str, error_message: str | None = None
    ) -> None:
        preview = await self.get_session(session_id)
        if preview:
            preview.status = status
            if error_message:
                preview.error_message = error_message
            if status == "completed":
                preview.completed_at = datetime.now(UTC)
            await self.session.commit()

    async def get_preview_data(
        self,
        session_id: UUID,
        table: str,
        page: int = 1,
        page_size: int = 100,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> dict:
        """Get preview data from source (PostgreSQL or S3)."""
        preview = await self.get_session(session_id)
        if not preview:
            return {"rows": [], "total": 0}
        if preview.status == "expired":
            raise ValueError("Preview session expired")
        if preview.status not in {"completed", "running"}:
            return {"rows": [], "total": 0}

        flow = await self._load_flow_for_preview(preview.flow_id)
        if not flow or not flow.source or not flow.source.credential:
            return {"rows": [], "total": 0}

        flow_table = self._resolve_flow_table(flow, table)
        self._ensure_table_allowed(preview, flow_table, table)
        if preview.resolved_mode == "snapshot":
            return self._get_snapshot_preview_data(
                preview=preview,
                flow_table=flow_table,
                requested_table=table,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        return await self._fetch_live_preview_data(
            flow=flow,
            flow_table=flow_table,
            row_limit=int(preview.row_limit),
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def _get_snapshot_preview_data(
        self,
        *,
        preview: PreviewSession,
        flow_table: FlowTable,
        requested_table: str,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_order: str,
    ) -> dict:
        snapshot_payload = preview.snapshot_payload if isinstance(preview.snapshot_payload, dict) else {}
        full_name = f"{flow_table.source_schema}.{flow_table.source_table}"
        table_payload = snapshot_payload.get(full_name)
        if table_payload is None:
            table_payload = snapshot_payload.get(requested_table)
        if table_payload is None:
            table_payload = snapshot_payload.get(str(flow_table.source_table))
        if not isinstance(table_payload, dict):
            return {"rows": [], "total": 0}

        columns = [str(item) for item in table_payload.get("columns", [])]
        rows = [
            {str(key): value for key, value in row.items()}
            for row in table_payload.get("rows", [])
            if isinstance(row, dict)
        ]
        if sort_by:
            sort_by = _validate_identifier(sort_by, "sort_by")
            if sort_by not in columns:
                raise ValueError("Invalid sort_by column")
            reverse = str(sort_order).lower() == "desc"
            rows.sort(
                key=lambda row: (row.get(sort_by) is None, str(row.get(sort_by) or "").lower()),
                reverse=reverse,
            )
        return self._build_paginated_preview_response(
            columns=columns,
            rows=rows,
            page=page,
            page_size=page_size,
        )

    async def _fetch_live_preview_data(
        self,
        *,
        flow: Flow,
        flow_table: FlowTable,
        row_limit: int,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_order: str,
    ) -> dict:
        source_type = str(flow.source.source_type or "").lower()
        if source_type == "s3":
            return await self._get_s3_preview_data(
                flow=flow,
                flow_table=flow_table,
                row_limit=row_limit,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        if source_type == "jira":
            return await self._get_jira_preview_data(
                flow=flow,
                flow_table=flow_table,
                row_limit=row_limit,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        schema_name, table_name = flow_table.source_schema, flow_table.source_table
        schema = _validate_identifier(schema_name, "schema")
        table_name = _validate_identifier(table_name, "table")
        offset = (page - 1) * page_size
        sort_order = "desc" if str(sort_order).lower() == "desc" else "asc"

        password = await decrypt_password(self.session, flow.source.credential.password_encrypted)
        conn = await asyncpg.connect(
            host=flow.source.host,
            port=flow.source.port,
            database=flow.source.database,
            user=flow.source.username,
            password=password,
            timeout=10,
        )

        try:
            cols = await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = $1 AND table_name = $2 "
                "ORDER BY ordinal_position",
                schema,
                table_name,
            )
            available_columns = [str(row["column_name"]) for row in cols]
            if not available_columns:
                return {"rows": [], "total": 0}
            if sort_by:
                sort_by = _validate_identifier(sort_by, "sort_by")
                if sort_by not in available_columns:
                    raise ValueError("Invalid sort_by column")

            quoted_schema = quote_ident(schema)
            quoted_table = quote_ident(table_name)
            total_raw = await conn.fetchval(f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}")
            total_source = int(total_raw or 0)
            total = min(total_source, int(row_limit))
            if offset >= total:
                return {
                    "columns": available_columns,
                    "rows": [],
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size if total else 0,
                }

            effective_limit = min(page_size, total - offset)
            order = f"ORDER BY {quote_ident(sort_by)} {sort_order}" if sort_by else ""
            rows_result = await conn.fetch(
                f"SELECT * FROM {quoted_schema}.{quoted_table} {order} LIMIT $1 OFFSET $2",
                effective_limit,
                offset,
            )
            rows = [dict(row) for row in rows_result]
        finally:
            await conn.close()

        return {
            "columns": available_columns,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
        }

    @staticmethod
    def _resolve_flow_table(flow: Flow, table: str) -> FlowTable:
        lookup = table.strip()

        # Prefer exact full-name match to support names containing dots
        # (for example S3 buckets/keys like "bucket.with.dots/file.csv").
        for ft in flow.tables:
            if f"{ft.source_schema}.{ft.source_table}" == lookup:
                return ft

        for ft in flow.tables:
            if ft.source_table == lookup:
                return ft
        raise ValueError("Table not configured in flow")

    @staticmethod
    def _ensure_table_allowed(
        preview: PreviewSession,
        flow_table: FlowTable,
        requested_table: str,
    ) -> None:
        allowed_raw = preview.tables_available or []
        allowed = {str(item) for item in allowed_raw if str(item).strip()}
        if not allowed:
            return

        full_name = f"{flow_table.source_schema}.{flow_table.source_table}"
        if requested_table in allowed or full_name in allowed or flow_table.source_table in allowed:
            return

        raise ValueError("Table not allowed in this preview session")

    @staticmethod
    def _normalize_preview_rows(rows: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for row in rows:
            normalized.append(flatten_record(row))
        return normalized

    @staticmethod
    def _build_preview_columns(rows: list[dict], schema_payload: dict | None = None) -> list[str]:
        columns: list[str] = []
        if isinstance(schema_payload, dict):
            schema = schema_payload.get("schema")
            properties = schema.get("properties") if isinstance(schema, dict) else None
            if isinstance(properties, dict):
                columns.extend(str(key) for key in properties.keys())
        for row in rows:
            for key in row.keys():
                key_str = str(key)
                if key_str not in columns:
                    columns.append(key_str)
        return columns

    @staticmethod
    def _build_paginated_preview_response(
        *,
        columns: list[str],
        rows: list[dict],
        page: int,
        page_size: int,
    ) -> dict:
        total = len(rows)
        offset = (page - 1) * page_size
        page_rows = rows[offset : offset + page_size] if offset < total else []
        return {
            "columns": columns,
            "rows": page_rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }

    async def _get_jira_preview_data(
        self,
        flow: Flow,
        flow_table: FlowTable,
        row_limit: int,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_order: str,
    ) -> dict:
        source_extraction = flow.source.extraction_config if isinstance(flow.source.extraction_config, dict) else {}
        flow_extraction = flow.extraction_config if isinstance(flow.extraction_config, dict) else {}
        config = JiraExtractionConfig.model_validate({**source_extraction, **flow_extraction})
        auth_type = config.auth_type
        requested_stream = str(flow_table.source_table).strip().lower()
        batch_size = min(max(int(row_limit), 1), 1000)
        password = await decrypt_password(self.session, flow.source.credential.password_encrypted)

        try:
            async with JiraService(flow.source.host, flow.source.username, password, auth_type=auth_type) as jira:
                payload = await jira.preview_records(
                    streams=[requested_stream],
                    project_keys=config.project_keys,
                    jql=config.jql,
                    query_mode=config.query_mode,
                    batch_size=batch_size,
                    start_date=config.start_date,
                )
        except Exception as exc:
            classified = JiraService.classify_error(exc)
            raise ValueError(classified.message) from exc

        normalized_rows = payload.get("rows_by_stream", {}).get(requested_stream)
        if isinstance(normalized_rows, list):
            rows = [row for row in normalized_rows if isinstance(row, dict)]
            schema_payload = payload.get("schema_by_stream", {}).get(requested_stream)
            columns = payload.get("columns_by_stream", {}).get(requested_stream) or self._build_preview_columns(
                rows,
                schema_payload=schema_payload if isinstance(schema_payload, dict) else None,
            )
        else:
            raw_rows = payload.get("records", {}).get(requested_stream, [])
            rows = self._normalize_preview_rows(
                [row for row in raw_rows if isinstance(row, dict)]
            )
            columns = self._build_preview_columns(rows)

        if sort_by:
            sort_by = _validate_identifier(sort_by, "sort_by")
            if sort_by not in columns:
                raise ValueError("Invalid sort_by column")
            reverse = str(sort_order).lower() == "desc"
            rows.sort(
                key=lambda row: (row.get(sort_by) is None, str(row.get(sort_by) or "").lower()),
                reverse=reverse,
            )

        return self._build_paginated_preview_response(
            columns=columns,
            rows=rows,
            page=page,
            page_size=page_size,
        )

    async def _get_s3_preview_data(
        self,
        flow: Flow,
        flow_table: FlowTable,
        row_limit: int,
        page: int,
        page_size: int,
        sort_by: str | None,
        sort_order: str,
    ) -> dict:
        password = await decrypt_password(self.session, flow.source.credential.password_encrypted)
        endpoint_url = build_s3_endpoint_url(flow.source.host, flow.source.port)

        def _download_sync() -> bytes:
            client = boto3.client(
                "s3",
                aws_access_key_id=flow.source.username,
                aws_secret_access_key=password,
                endpoint_url=endpoint_url,
            )
            response = client.get_object(Bucket=flow.source.database, Key=flow_table.source_table)
            return bytes(response["Body"].read())

        try:
            object_bytes = await asyncio.to_thread(_download_sync)
        except (ClientError, BotoCoreError) as exc:
            raise ValueError(f"S3 preview error: {exc}") from exc

        limit = max(1, int(row_limit))
        columns, matrix_rows = parse_s3_object_rows(
            flow_table.source_table,
            object_bytes,
            row_limit=limit,
        )
        if not columns:
            return {
                "columns": [],
                "rows": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0,
            }

        if sort_by and sort_by not in columns:
            raise ValueError("Invalid sort_by column")

        order_desc = str(sort_order).lower() == "desc"
        if sort_by:
            sort_idx = columns.index(sort_by)
            matrix_rows.sort(
                key=lambda row: (row[sort_idx] is None, str(row[sort_idx] or "").lower()),
                reverse=order_desc,
            )

        total = len(matrix_rows)
        offset = (page - 1) * page_size
        if offset >= total:
            return {
                "columns": columns,
                "rows": [],
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
            }

        page_rows = matrix_rows[offset : offset + page_size]
        rows = [dict(zip(columns, values, strict=False)) for values in page_rows]

        return {
            "columns": columns,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }
