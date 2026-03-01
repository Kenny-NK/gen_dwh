"""Schedule model - tenant schema (T073)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("flow_id"),
        Index("idx_schedules_flow", "flow_id"),
        Index("idx_schedules_next_run", "next_run_at"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    flow_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id", ondelete="CASCADE"), nullable=False
    )

    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)  # cron, interval, manual
    cron_expression: Mapped[str | None] = mapped_column(String(100))
    interval_minutes: Mapped[int | None] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Europe/Moscow")

    # Execution constraints
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    timeout_minutes: Mapped[int] = mapped_column(Integer, default=120)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.users.id")
    )

    # Relationships
    flow: Mapped["Flow"] = relationship(back_populates="schedule")
