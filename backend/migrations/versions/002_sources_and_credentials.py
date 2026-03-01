"""Sources and source_credentials tables (T037).

Revision ID: 002_sources
Revises: 001_initial
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "002_sources"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: These tables are created per-tenant schema.
    # This migration serves as a template for tenant schema creation.
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default=sa.text("5432")),
        sa.Column("database", sa.String(255), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("connection_status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.Column("validation_error", sa.Text()),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("public.users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_sources_status", "sources", ["connection_status"])

    op.create_table(
        "source_credentials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("password_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("rotation_due_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("source_credentials")
    op.drop_table("sources")
