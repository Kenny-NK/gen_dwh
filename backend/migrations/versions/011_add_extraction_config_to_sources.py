"""Add extraction_config to sources for Jira connector.

Revision ID: 011_source_extraction_cfg
Revises: 010_run_source_guards
Create Date: 2026-03-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011_source_extraction_cfg"
down_revision: Union[str, None] = "010_run_source_guards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("extraction_config", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("sources", "extraction_config")
