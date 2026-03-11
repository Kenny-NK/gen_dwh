"""Add hard-cancel and source-deletion guard fields.

Revision ID: 010_run_source_guards
Revises: 009_run_source_volume_progress
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_run_source_guards"
down_revision: Union[str, None] = "009_run_source_volume_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("celery_task_id", sa.String(length=255), nullable=True))

    op.add_column(
        "flows",
        sa.Column(
            "source_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "flows",
        sa.Column(
            "pause_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.drop_constraint("flows_source_id_fkey", "flows", type_="foreignkey")
    op.alter_column("flows", "source_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key(
        "flows_source_id_fkey",
        "flows",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("flows_source_id_fkey", "flows", type_="foreignkey")
    op.create_foreign_key(
        "flows_source_id_fkey",
        "flows",
        "sources",
        ["source_id"],
        ["id"],
    )
    op.alter_column("flows", "source_id", existing_type=sa.UUID(), nullable=False)

    op.drop_column("flows", "pause_requested")
    op.drop_column("flows", "source_deleted")
    op.drop_column("runs", "celery_task_id")
