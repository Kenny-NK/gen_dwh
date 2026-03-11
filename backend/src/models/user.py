"""Global user model stored in the public schema."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_keycloak", "keycloak_id"),
        Index("idx_users_email", "email"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keycloak_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memberships: Mapped[list[WorkspaceMembership]] = relationship(back_populates="user")
