"""Notification model - tenant schema (T097)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, now_utc


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user", "user_id"),
        Index("idx_notifications_created", "created_at"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("public.users.id"))
    is_broadcast: Mapped[bool] = mapped_column(Boolean, default=False)

    type: Mapped[str] = mapped_column(String(20), nullable=False)  # success, error, warning, info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    related_entity_type: Mapped[str | None] = mapped_column(String(50))
    related_entity_id: Mapped[PyUUID | None] = mapped_column(UUID(as_uuid=True))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now()
    )
