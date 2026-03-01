"""Preview execution service (T056, T057)."""

from datetime import UTC, datetime, timedelta
import re
from uuid import UUID

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.flow import Flow
from src.models.preview_session import PreviewSession
from src.models.source import Source
from src.services.connection import decrypt_password

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
        """Get preview data directly from source PostgreSQL."""
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

        schema_name, table_name = self._resolve_source_table(flow, table)
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
    def _resolve_source_table(flow: Flow, table: str) -> tuple[str, str]:
        lookup = table.strip()
        if "." in lookup:
            schema_name, table_name = lookup.split(".", 1)
            for ft in flow.tables:
                if ft.source_schema == schema_name and ft.source_table == table_name:
                    return schema_name, table_name
            raise ValueError("Table not configured in flow")

        for ft in flow.tables:
            if ft.source_table == lookup:
                return ft.source_schema, ft.source_table
        raise ValueError("Table not configured in flow")
