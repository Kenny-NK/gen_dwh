"""Per-user read receipts for broadcast notifications."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, now_utc


class NotificationRead(Base):
    __tablename__ = "notification_reads"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id"),
        Index("idx_notification_reads_user", "user_id"),
        Index("idx_notification_reads_notification", "notification_id"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    notification_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now(), nullable=False
    )
