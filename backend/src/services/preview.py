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

from src.models.flow import Flow
from src.models.flow_table import FlowTable
from src.models.preview_session import PreviewSession
from src.models.source import Source
from src.services.connection import build_s3_endpoint_url, decrypt_password
from src.services.s3_loader import parse_s3_object_rows

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _validate_identifier(value: str, field: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class PreviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(
        self,
        flow_id: UUID,
        row_limit: int = 100,
        tables_available: list[str] | None = None,
    ) -> PreviewSession:
        """Create a new preview session."""
        preview = PreviewSession(
            flow_id=flow_id,
            row_limit=min(row_limit, 10000),
            status="completed",
            tables_available=tables_available,
            completed_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self.session.add(preview)
        await self.session.flush()
        await self.session.commit()
        return preview

    async def get_session(self, session_id: UUID) -> PreviewSession | None:
        result = await self.session.execute(
            select(PreviewSession).where(PreviewSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_session_for_flow(self, session_id: UUID, flow_id: UUID) -> PreviewSession | None:
        result = await self.session.execute(
            select(PreviewSession).where(
                PreviewSession.id == session_id,
                PreviewSession.flow_id == flow_id,
            )
        )
        return result.scalar_one_or_none()

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
        if not preview or preview.status not in {"completed", "running"}:
            return {"rows": [], "total": 0}

        flow_result = await self.session.execute(
            select(Flow)
            .options(
                selectinload(Flow.tables),
                selectinload(Flow.source).selectinload(Source.credential),
            )
            .where(Flow.id == preview.flow_id)
        )
        flow = flow_result.scalar_one_or_none()
        if not flow or not flow.source or not flow.source.credential:
            return {"rows": [], "total": 0}

        flow_table = self._resolve_flow_table(flow, table)
        self._ensure_table_allowed(preview, flow_table, table)
        if str(flow.source.source_type or "").lower() == "s3":
            return await self._get_s3_preview_data(
                flow=flow,
                flow_table=flow_table,
                preview=preview,
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

            quoted_schema = _quote_ident(schema)
            quoted_table = _quote_ident(table_name)
            total_raw = await conn.fetchval(f"SELECT COUNT(*) FROM {quoted_schema}.{quoted_table}")
            total_source = int(total_raw or 0)
            total = min(total_source, int(preview.row_limit))
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
            order = f"ORDER BY {_quote_ident(sort_by)} {sort_order}" if sort_by else ""
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

    async def _get_s3_preview_data(
        self,
        flow: Flow,
        flow_table: FlowTable,
        preview: PreviewSession,
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

        limit = max(1, int(preview.row_limit))
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
