"""FlowTable model (T052)."""

from uuid import UUID as PyUUID, uuid4

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class FlowTable(Base, TimestampMixin):
    __tablename__ = "flow_tables"
    __table_args__ = (
        UniqueConstraint("flow_id", "source_schema", "source_table"),
        Index("idx_flow_tables_flow", "flow_id"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    flow_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )

    # Source table selection
    source_schema: Mapped[str] = mapped_column(String(255), nullable=False)
    source_table: Mapped[str] = mapped_column(String(255), nullable=False)

    # Target table name
    target_table: Mapped[str] = mapped_column(String(255), nullable=False)

    # Replication configuration
    replication_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="FULL_TABLE"
    )
    replication_key: Mapped[str | None] = mapped_column(String(255))

    # Column selection
    selected_columns: Mapped[list[str] | None] = mapped_column(JSONB)
    sensitive_columns: Mapped[dict | None] = mapped_column(JSONB)

    # State tracking
    last_cursor_value: Mapped[str | None] = mapped_column(Text)

    # Relationships
    flow: Mapped["Flow"] = relationship(back_populates="tables")
