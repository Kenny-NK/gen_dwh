"""Introduce workspace memberships and global users.

Revision ID: 012_workspace_memberships
Revises: 011_source_extraction_cfg
Create Date: 2026-03-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "012_workspace_memberships"
down_revision: Union[str, None] = "011_source_extraction_cfg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        schema="public",
    )

    op.drop_constraint("users_tenant_id_keycloak_id_key", "users", schema="public", type_="unique")
    op.drop_index("idx_users_tenant", table_name="users", schema="public")
    op.drop_column("users", "tenant_id", schema="public")
    op.drop_column("users", "role", schema="public")
    op.create_index("idx_users_email", "users", ["email"], schema="public")
    op.create_unique_constraint("uq_users_keycloak_id", "users", ["keycloak_id"], schema="public")

    op.create_table(
        "workspace_memberships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("public.tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "tenant_id"),
        schema="public",
    )
    op.create_index(
        "idx_workspace_memberships_user",
        "workspace_memberships",
        ["user_id"],
        schema="public",
    )
    op.create_index(
        "idx_workspace_memberships_tenant",
        "workspace_memberships",
        ["tenant_id"],
        schema="public",
    )


def downgrade() -> None:
    op.drop_index("idx_workspace_memberships_tenant", table_name="workspace_memberships", schema="public")
    op.drop_index("idx_workspace_memberships_user", table_name="workspace_memberships", schema="public")
    op.drop_table("workspace_memberships", schema="public")

    op.drop_constraint("uq_users_keycloak_id", "users", schema="public", type_="unique")
    op.drop_index("idx_users_email", table_name="users", schema="public")
    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=False), schema="public")
    op.add_column(
        "users",
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        schema="public",
    )
    op.create_index("idx_users_tenant", "users", ["tenant_id"], schema="public")
    op.create_foreign_key(
        "users_tenant_id_fkey",
        "users",
        "tenants",
        ["tenant_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "users_tenant_id_keycloak_id_key",
        "users",
        ["tenant_id", "keycloak_id"],
        schema="public",
    )
    op.alter_column("users", "tenant_id", existing_type=UUID(as_uuid=True), nullable=False, schema="public")

    op.drop_column("tenants", "deleted_at", schema="public")
