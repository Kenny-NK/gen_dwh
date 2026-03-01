"""Add unique constraint for run_number per flow.

Revision ID: 006_run_number_uniqueness
Revises: 005_monitoring
Create Date: 2026-03-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "006_run_number_uniqueness"
down_revision: Union[str, None] = "005_monitoring"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_runs_flow_run_number",
        "runs",
        ["flow_id", "run_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_runs_flow_run_number", "runs", type_="unique")
