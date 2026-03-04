"""Run model - tenant schema (T072)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, now_utc


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("flow_id", "run_number"),
        Index("idx_runs_flow", "flow_id"),
        Index("idx_runs_status", "status"),
        Index("idx_runs_created", "created_at"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    flow_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id"), nullable=False
    )

    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)  # manual, scheduled, retry

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Metrics
    tables_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_processed: Mapped[int] = mapped_column(BigInteger, default=0)
    source_records_total: Mapped[int | None] = mapped_column(BigInteger)
    source_records_total_is_estimate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )
    records_failed: Mapped[int] = mapped_column(BigInteger, default=0)

    # Error information
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[dict | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Meltano state
    meltano_state_file: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now()
    )

    # Relationships
    flow: Mapped["Flow"] = relationship(back_populates="runs")
