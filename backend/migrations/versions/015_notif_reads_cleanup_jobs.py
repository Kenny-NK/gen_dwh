"""Add notification read receipts and durable cleanup jobs to tenant schemas.

Revision ID: 015_notif_reads_cleanup_jobs
Revises: 014_preview_modes_and_sessions
Create Date: 2026-03-11
"""

from __future__ import annotations

import re
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_notif_reads_cleanup_jobs"
down_revision: Union[str, None] = "014_preview_modes_and_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _tenant_schemas() -> list[str]:
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            """
            SELECT schema_name
            FROM public.tenants
            ORDER BY created_at ASC
            """
        )
    )
    schemas: list[str] = []
    for row in result:
        schema_name = str(row[0])
        if _SCHEMA_RE.fullmatch(schema_name):
            schemas.append(schema_name)
    return schemas


def _quoted_schema(schema_name: str) -> str:
    return '"' + schema_name.replace('"', '""') + '"'


def upgrade() -> None:
    bind = op.get_bind()
    for schema_name in _tenant_schemas():
        schema = _quoted_schema(schema_name)
        bind.execute(
            sa.text(
                f"""
                CREATE TABLE IF NOT EXISTS {schema}.notification_reads (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    notification_id UUID NOT NULL
                        REFERENCES {schema}.notifications(id) ON DELETE CASCADE,
                    user_id UUID NOT NULL
                        REFERENCES public.users(id) ON DELETE CASCADE,
                    read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (notification_id, user_id)
                )
                """
            )
        )
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_notification_reads_user
                ON {schema}.notification_reads (user_id)
                """
            )
        )
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_notification_reads_notification
                ON {schema}.notification_reads (notification_id)
                """
            )
        )
        bind.execute(
            sa.text(
                f"""
                CREATE TABLE IF NOT EXISTS {schema}.cleanup_jobs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    job_type VARCHAR(50) NOT NULL DEFAULT 'drop_table',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    target_schema VARCHAR(63) NOT NULL,
                    target_table VARCHAR(255) NOT NULL,
                    requested_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
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
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cleanup_jobs_status_available
                ON {schema}.cleanup_jobs (status, available_at)
                """
            )
        )
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cleanup_jobs_related_entity
                ON {schema}.cleanup_jobs (related_entity_type, related_entity_id)
                """
            )
        )
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cleanup_jobs_requested_by
                ON {schema}.cleanup_jobs (requested_by)
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for schema_name in _tenant_schemas():
        schema = _quoted_schema(schema_name)
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {schema}.cleanup_jobs"))
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {schema}.notification_reads"))
