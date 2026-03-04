"""Add source_type and extend flow table identifier lengths.

Revision ID: 008_s3_sources
Revises: 007_soft_delete_indexes
Create Date: 2026-03-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008_s3_sources"
down_revision: Union[str, None] = "007_soft_delete_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column(
            "source_type",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'postgres'"),
        ),
    )
    op.create_index("idx_sources_type", "sources", ["source_type"])

    op.alter_column(
        "flow_tables",
        "source_schema",
        existing_type=sa.String(length=63),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "flow_tables",
        "source_table",
        existing_type=sa.String(length=63),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "flow_tables",
        "target_table",
        existing_type=sa.String(length=63),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "flow_tables",
        "target_table",
        existing_type=sa.String(length=255),
        type_=sa.String(length=63),
        existing_nullable=False,
    )
    op.alter_column(
        "flow_tables",
        "source_table",
        existing_type=sa.String(length=255),
        type_=sa.String(length=63),
        existing_nullable=False,
    )
    op.alter_column(
        "flow_tables",
        "source_schema",
        existing_type=sa.String(length=255),
        type_=sa.String(length=63),
        existing_nullable=False,
    )

    op.drop_index("idx_sources_type", table_name="sources")
    op.drop_column("sources", "source_type")
