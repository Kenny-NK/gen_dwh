"""SourceCredential model with encryption (T036)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, ForeignKey, LargeBinary, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, now_utc


class SourceCredential(Base):
    __tablename__ = "source_credentials"
    __table_args__ = (
        UniqueConstraint("source_id"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    password_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Rotation tracking
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotation_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now()
    )

    # Relationships
    source: Mapped["Source"] = relationship(back_populates="credential")
