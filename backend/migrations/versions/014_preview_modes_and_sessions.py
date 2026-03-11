"""Add flow preview mode and preview session policy fields.

Revision ID: 014_preview_modes_and_sessions
Revises: 013_flow_extraction_config
Create Date: 2026-03-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "014_preview_modes_and_sessions"
down_revision: Union[str, None] = "013_flow_extraction_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flows",
        sa.Column("preview_mode", sa.String(length=20), nullable=False, server_default="auto"),
    )
    op.add_column("preview_sessions", sa.Column("requested_mode", sa.String(length=20), nullable=True))
    op.add_column(
        "preview_sessions",
        sa.Column("resolved_mode", sa.String(length=20), nullable=False, server_default="live"),
    )
    op.add_column("preview_sessions", sa.Column("snapshot_payload", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("preview_sessions", "snapshot_payload")
    op.drop_column("preview_sessions", "resolved_mode")
    op.drop_column("preview_sessions", "requested_mode")
    op.drop_column("flows", "preview_mode")
