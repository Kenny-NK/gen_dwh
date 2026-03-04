"""Add run source-volume progress fields.

Revision ID: 009_run_source_volume_progress
Revises: 008_s3_sources
Create Date: 2026-03-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009_run_source_volume_progress"
down_revision: Union[str, None] = "008_s3_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("source_records_total", sa.BigInteger(), nullable=True))
    op.add_column(
        "runs",
        sa.Column(
            "source_records_total_is_estimate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "source_records_total_is_estimate")
    op.drop_column("runs", "source_records_total")
