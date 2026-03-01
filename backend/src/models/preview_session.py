"""PreviewSession model (T053)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, now_utc


class PreviewSession(Base):
    __tablename__ = "preview_sessions"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    flow_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    row_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    total_rows: Mapped[int | None] = mapped_column(Integer)
    tables_available: Mapped[list | None] = mapped_column(JSONB)

    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
