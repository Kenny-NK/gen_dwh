"""Durable tenant-scoped cleanup jobs for business DB resources."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin, now_utc


class CleanupJob(Base, TimestampMixin):
    __tablename__ = "cleanup_jobs"
    __table_args__ = (
        Index("idx_cleanup_jobs_status_available", "status", "available_at"),
        Index("idx_cleanup_jobs_related_entity", "related_entity_type", "related_entity_id"),
        Index("idx_cleanup_jobs_requested_by", "requested_by"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="drop_table",
        server_default="drop_table",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    target_schema: Mapped[str] = mapped_column(String(63), nullable=False)
    target_table: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="SET NULL"),
    )
    related_entity_type: Mapped[str | None] = mapped_column(String(50))
    related_entity_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=8,
        server_default="8",
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=now_utc,
        server_default=func.now(),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
