"""Bootstrap system DB for local/dev deployments.

- Applies Alembic migrations (or stamps head for legacy pre-migration schemas).
- Ensures at least one active tenant exists.
- Ensures tenant schema(s) and tenant-scoped tables exist.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import Iterable

from sqlalchemy import select, text

from src.core.config import settings
from src.core.tenant import validate_schema_name
from src.models.base import Base, SystemSessionLocal, system_engine
from src.models.tenant import Tenant

# Import models so metadata includes all tenant-scoped tables.
import src.models.audit  # noqa: F401
import src.models.flow  # noqa: F401
import src.models.flow_table  # noqa: F401
import src.models.notification  # noqa: F401
import src.models.preview_session  # noqa: F401
import src.models.run  # noqa: F401
import src.models.schedule  # noqa: F401
import src.models.source  # noqa: F401
import src.models.source_credential  # noqa: F401
import src.models.user  # noqa: F401


async def _table_exists(schema: str, table: str) -> bool:
    async with system_engine.connect() as conn:
        result = await conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = :schema_name
                      AND table_name = :table_name
                )
                """
            ),
            {"schema_name": schema, "table_name": table},
        )
        return bool(result.scalar())


def _run_alembic(*args: str) -> None:
    subprocess.run(["alembic", *args], check=True)


async def _apply_migrations() -> None:
    has_tenants = await _table_exists("public", "tenants")
    has_alembic_version = await _table_exists("public", "alembic_version")

    if has_tenants and not has_alembic_version:
        print("Detected legacy schema without alembic_version, stamping head")
        _run_alembic("stamp", "head")
        return

    print("Applying Alembic migrations")
    _run_alembic("upgrade", "head")


async def _ensure_pgcrypto() -> None:
    # Some legacy/stamped environments may miss extension creation from migrations.
    async with system_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))


async def _ensure_default_tenant() -> None:
    async with SystemSessionLocal() as session:
        result = await session.execute(
            select(Tenant.id).where(Tenant.is_active.is_(True)).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return

        tenant = Tenant(
            subdomain=settings.bootstrap_tenant_subdomain,
            schema_name=validate_schema_name(settings.bootstrap_tenant_schema),
            keycloak_realm=settings.keycloak_realm,
            name=settings.bootstrap_tenant_name,
            is_active=True,
        )
        session.add(tenant)
        await session.commit()
        print(
            "Created default tenant:",
            settings.bootstrap_tenant_subdomain,
            settings.bootstrap_tenant_schema,
        )


async def _get_active_tenant_schemas() -> list[str]:
    async with SystemSessionLocal() as session:
        result = await session.execute(
            select(Tenant.schema_name)
            .where(Tenant.is_active.is_(True))
            .order_by(Tenant.created_at.asc())
        )
        return [validate_schema_name(schema) for schema in result.scalars().all()]


def _tenant_tables() -> Iterable:
    # Tenant-scoped tables are defined without explicit schema.
    return [table for table in Base.metadata.tables.values() if table.schema is None]


async def _ensure_tenant_schema_tables() -> None:
    tenant_tables = list(_tenant_tables())
    schemas = await _get_active_tenant_schemas()

    for schema_name in schemas:
        async with system_engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            # Force table creation checks in tenant schema, not in public.
            await conn.execute(text(f'SET LOCAL search_path TO "{schema_name}"'))
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tenant_tables)
            )
        print(f"Ensured tenant schema and tables: {schema_name}")


async def _ensure_tenant_schema_compatibility() -> None:
    """Apply lightweight, idempotent schema upgrades for tenant tables."""
    schemas = await _get_active_tenant_schemas()
    for schema_name in schemas:
        async with system_engine.begin() as conn:
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE "{schema_name}".sources
                    ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'postgres'
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_sources_type
                    ON "{schema_name}".sources (source_type)
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE "{schema_name}".flow_tables
                    ALTER COLUMN source_schema TYPE VARCHAR(255)
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE "{schema_name}".flow_tables
                    ALTER COLUMN source_table TYPE VARCHAR(255)
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE "{schema_name}".flow_tables
                    ALTER COLUMN target_table TYPE VARCHAR(255)
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE "{schema_name}".runs
                    ADD COLUMN IF NOT EXISTS source_records_total BIGINT
                    """
                )
            )
            await conn.execute(
                text(
                    f"""
                    ALTER TABLE "{schema_name}".runs
                    ADD COLUMN IF NOT EXISTS source_records_total_is_estimate BOOLEAN NOT NULL DEFAULT true
                    """
                )
            )
        print(f"Ensured tenant schema compatibility upgrades: {schema_name}")


async def main() -> None:
    await _apply_migrations()
    await _ensure_pgcrypto()
    await _ensure_default_tenant()
    await _ensure_tenant_schema_tables()
    await _ensure_tenant_schema_compatibility()
    print("Backend bootstrap completed")


if __name__ == "__main__":
    asyncio.run(main())
