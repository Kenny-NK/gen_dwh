"""Move Jira extraction config to flows.

Revision ID: 013_flow_extraction_config
Revises: 012_workspace_memberships
Create Date: 2026-03-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "013_flow_extraction_config"
down_revision: Union[str, None] = "012_workspace_memberships"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("flows", sa.Column("extraction_config", JSONB(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE flows
            SET extraction_config = sources.extraction_config
            FROM sources
            WHERE flows.source_id = sources.id
              AND sources.source_type = 'jira'
              AND sources.extraction_config IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("flows", "extraction_config")
