"""Source model - tenant schema (T035)."""

from datetime import datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Source(Base, TimestampMixin):
    __tablename__ = "sources"
    __table_args__ = (
        Index("idx_sources_status", "connection_status"),
        Index("idx_sources_deleted_at", "deleted_at"),
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Connection parameters
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    database: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)

    # Validation status
    connection_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_error: Mapped[str | None] = mapped_column(Text)

    # Metadata
    created_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.users.id")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    credential: Mapped["SourceCredential"] = relationship(
        back_populates="source", uselist=False, cascade="all, delete-orphan"
    )
    flows: Mapped[list["Flow"]] = relationship(back_populates="source")
