"""Workspace model stored in the public schema."""

from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = (
        Index("idx_tenants_subdomain", "subdomain"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subdomain: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    keycloak_realm: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[WorkspaceMembership]] = relationship(back_populates="workspace")
