"""Add schedule uniqueness and soft-delete indexes.

Revision ID: 007_schedule_uniqueness_and_soft_delete_indexes
Revises: 006_run_number_uniqueness
Create Date: 2026-03-01
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007_schedule_uniqueness_and_soft_delete_indexes"
down_revision: Union[str, None] = "006_run_number_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_schedules_flow_id", "schedules", ["flow_id"])
    op.create_index("idx_flows_deleted_at", "flows", ["deleted_at"])
    op.create_index("idx_sources_deleted_at", "sources", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("idx_sources_deleted_at", table_name="sources")
    op.drop_index("idx_flows_deleted_at", table_name="flows")
    op.drop_constraint("uq_schedules_flow_id", "schedules", type_="unique")
