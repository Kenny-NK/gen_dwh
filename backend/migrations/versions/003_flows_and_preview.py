"""Flows, flow_tables, preview_sessions tables (T054).

Revision ID: 003_flows
Revises: 002_sources
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "003_flows"
down_revision: Union[str, None] = "002_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "flows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("target_schema", sa.String(63), nullable=False),
        sa.Column("target_table_prefix", sa.String(63)),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("status_reason", sa.Text()),
        sa.Column("write_mode", sa.String(20), nullable=False, server_default=sa.text("'append'")),
        sa.Column("upsert_key", sa.String(255)),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("public.users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_flows_source", "flows", ["source_id"])
    op.create_index("idx_flows_status", "flows", ["status"])

    op.create_table(
        "flow_tables",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("flow_id", UUID(as_uuid=True), sa.ForeignKey("flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_schema", sa.String(63), nullable=False),
        sa.Column("source_table", sa.String(63), nullable=False),
        sa.Column("target_table", sa.String(63), nullable=False),
        sa.Column("replication_method", sa.String(20), nullable=False, server_default=sa.text("'FULL_TABLE'")),
        sa.Column("replication_key", sa.String(255)),
        sa.Column("selected_columns", JSONB()),
        sa.Column("sensitive_columns", JSONB()),
        sa.Column("last_cursor_value", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("flow_id", "source_schema", "source_table"),
    )
    op.create_index("idx_flow_tables_flow", "flow_tables", ["flow_id"])

    op.create_table(
        "preview_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("flow_id", UUID(as_uuid=True), sa.ForeignKey("flows.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("row_limit", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("total_rows", sa.Integer()),
        sa.Column("tables_available", JSONB()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("preview_sessions")
    op.drop_table("flow_tables")
    op.drop_table("flows")
