"""Initial public schema - tenants and users (T014).

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgcrypto extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("subdomain", sa.String(63), unique=True, nullable=False),
        sa.Column("schema_name", sa.String(63), unique=True, nullable=False),
        sa.Column("keycloak_realm", sa.String(100)),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="public",
    )
    op.create_index("idx_tenants_subdomain", "tenants", ["subdomain"], schema="public")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("public.tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keycloak_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "keycloak_id"),
        schema="public",
    )
    op.create_index("idx_users_tenant", "users", ["tenant_id"], schema="public")
    op.create_index("idx_users_keycloak", "users", ["keycloak_id"], schema="public")


def downgrade() -> None:
    op.drop_table("users", schema="public")
    op.drop_table("tenants", schema="public")
