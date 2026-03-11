"""Flow model - tenant schema (T051)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Flow(Base, TimestampMixin):
    __tablename__ = "flows"
    __table_args__ = (
        Index("idx_flows_source", "source_id"),
        Index("idx_flows_status", "status"),
        Index("idx_flows_deleted_at", "deleted_at"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Source reference
    source_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    # Target configuration
    target_schema: Mapped[str] = mapped_column(String(63), nullable=False)
    target_table_prefix: Mapped[str | None] = mapped_column(String(63))

    # Flow state
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    status_reason: Mapped[str | None] = mapped_column(Text)
    source_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    pause_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # Write configuration
    write_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="append")
    upsert_key: Mapped[str | None] = mapped_column(String(255))
    extraction_config: Mapped[dict | None] = mapped_column(JSONB)
    preview_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="auto",
        server_default="auto",
    )

    # Metadata
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.users.id")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    source: Mapped["Source | None"] = relationship(back_populates="flows")
    tables: Mapped[list["FlowTable"]] = relationship(
        back_populates="flow", cascade="all, delete-orphan"
    )
    runs: Mapped[list["Run"]] = relationship(back_populates="flow")
    schedule: Mapped["Schedule | None"] = relationship(
        back_populates="flow", uselist=False, cascade="all, delete-orphan"
    )
