"""Tenant schema provisioning helpers shared by bootstrap and admin flows."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from src.models.base import Base, system_engine

_checked_tenant_schemas: set[str] = set()
_tenant_schema_lock = asyncio.Lock()


def tenant_tables() -> Iterable:
    return [table for table in Base.metadata.tables.values() if table.schema is None]


async def ensure_tenant_schema_tables(
    conn: AsyncConnection,
    schema_name: str,
) -> None:
    await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
    await conn.execute(text(f'SET LOCAL search_path TO "{schema_name}"'))
    await conn.run_sync(
        lambda sync_conn: Base.metadata.create_all(sync_conn, tables=list(tenant_tables()))
    )


async def ensure_tenant_schema_compatibility(
    conn: AsyncConnection,
    schema_name: str,
) -> None:
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
            ALTER TABLE "{schema_name}".sources
            ADD COLUMN IF NOT EXISTS extraction_config JSONB
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
            ALTER TABLE "{schema_name}".flows
            ADD COLUMN IF NOT EXISTS extraction_config JSONB
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".flows
            ADD COLUMN IF NOT EXISTS source_deleted BOOLEAN NOT NULL DEFAULT false
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".flows
            ADD COLUMN IF NOT EXISTS pause_requested BOOLEAN NOT NULL DEFAULT false
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".flows
            ADD COLUMN IF NOT EXISTS preview_mode VARCHAR(20) NOT NULL DEFAULT 'auto'
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".flows
            ALTER COLUMN source_id DROP NOT NULL
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".flows
            DROP CONSTRAINT IF EXISTS flows_source_id_fkey
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".flows
            ADD CONSTRAINT flows_source_id_fkey
            FOREIGN KEY (source_id)
            REFERENCES "{schema_name}".sources(id)
            ON DELETE SET NULL
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
            ALTER TABLE "{schema_name}".preview_sessions
            ADD COLUMN IF NOT EXISTS requested_mode VARCHAR(20)
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".preview_sessions
            ADD COLUMN IF NOT EXISTS resolved_mode VARCHAR(20) NOT NULL DEFAULT 'live'
            """
        )
    )
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".preview_sessions
            ADD COLUMN IF NOT EXISTS snapshot_payload JSONB
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
    await conn.execute(
        text(
            f"""
            ALTER TABLE "{schema_name}".runs
            ADD COLUMN IF NOT EXISTS celery_task_id VARCHAR(255)
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema_name}".notification_reads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                notification_id UUID NOT NULL
                    REFERENCES "{schema_name}".notifications(id) ON DELETE CASCADE,
                user_id UUID NOT NULL
                    REFERENCES public.users(id) ON DELETE CASCADE,
                read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (notification_id, user_id)
            )
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_notification_reads_user
            ON "{schema_name}".notification_reads (user_id)
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_notification_reads_notification
            ON "{schema_name}".notification_reads (notification_id)
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS "{schema_name}".cleanup_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_type VARCHAR(50) NOT NULL DEFAULT 'drop_table',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                target_schema VARCHAR(63) NOT NULL,
                target_table VARCHAR(255) NOT NULL,
                requested_by UUID
                    REFERENCES public.users(id) ON DELETE SET NULL,
                related_entity_type VARCHAR(50),
                related_entity_id UUID,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 8,
                available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_attempt_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_cleanup_jobs_status_available
            ON "{schema_name}".cleanup_jobs (status, available_at)
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_cleanup_jobs_related_entity
            ON "{schema_name}".cleanup_jobs (related_entity_type, related_entity_id)
            """
        )
    )
    await conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS idx_cleanup_jobs_requested_by
            ON "{schema_name}".cleanup_jobs (requested_by)
            """
        )
    )


async def provision_tenant_schema(schema_name: str) -> None:
    async with system_engine.begin() as conn:
        await ensure_tenant_schema_tables(conn, schema_name)
        await ensure_tenant_schema_compatibility(conn, schema_name)


async def ensure_tenant_schema_compatibility_once(schema_name: str) -> None:
    if schema_name in _checked_tenant_schemas:
        return
    async with _tenant_schema_lock:
        if schema_name in _checked_tenant_schemas:
            return
        await provision_tenant_schema(schema_name)
        _checked_tenant_schemas.add(schema_name)
