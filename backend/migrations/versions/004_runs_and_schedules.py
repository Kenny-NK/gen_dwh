"""Runs and schedules tables (T074).

Revision ID: 004_runs
Revises: 003_flows
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "004_runs"
down_revision: Union[str, None] = "003_flows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("flow_id", UUID(as_uuid=True), sa.ForeignKey("flows.id"), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("triggered_by", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("tables_processed", sa.Integer(), server_default=sa.text("0")),
        sa.Column("records_processed", sa.BigInteger(), server_default=sa.text("0")),
        sa.Column("records_failed", sa.BigInteger(), server_default=sa.text("0")),
        sa.Column("error_message", sa.Text()),
        sa.Column("error_details", JSONB()),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("meltano_state_file", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_runs_flow", "runs", ["flow_id"])
    op.create_index("idx_runs_status", "runs", ["status"])
    op.create_index("idx_runs_created", "runs", ["created_at"])

    op.create_table(
        "schedules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("flow_id", UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("schedule_type", sa.String(20), nullable=False),
        sa.Column("cron_expression", sa.String(100)),
        sa.Column("interval_minutes", sa.Integer()),
        sa.Column("timezone", sa.String(50), nullable=False, server_default=sa.text("'Europe/Moscow'")),
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("5")),
        sa.Column("timeout_minutes", sa.Integer(), server_default=sa.text("120")),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("public.users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_schedules_flow", "schedules", ["flow_id"])
    op.create_index("idx_schedules_next_run", "schedules", ["next_run_at"])


def downgrade() -> None:
    op.drop_table("schedules")
    op.drop_table("runs")
