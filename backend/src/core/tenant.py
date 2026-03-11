"""Tenant context management middleware (T017)."""

from contextvars import ContextVar
import re
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_utils import quote_ident

current_tenant_id: ContextVar[UUID | None] = ContextVar("current_tenant_id", default=None)
current_tenant_schema: ContextVar[str | None] = ContextVar("current_tenant_schema", default=None)
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def validate_schema_name(schema_name: str) -> str:
    """Validate tenant schema identifier used in search_path."""
    if not _SCHEMA_RE.fullmatch(schema_name):
        raise ValueError("Invalid tenant schema name")
    return schema_name


async def set_tenant_schema(session: AsyncSession, schema_name: str) -> None:
    """Set the search_path for the current database session to the tenant schema."""
    validated = validate_schema_name(schema_name)
    await session.execute(text(f"SET search_path TO {quote_ident(validated)}, public"))


def get_current_tenant_id() -> UUID | None:
    return current_tenant_id.get()


def get_current_tenant_schema() -> str | None:
    return current_tenant_schema.get()
