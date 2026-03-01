"""User model - public schema (T013)."""

from uuid import UUID as PyUUID, uuid4

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "keycloak_id"),
        Index("idx_users_tenant", "tenant_id"),
        Index("idx_users_keycloak", "keycloak_id"),
        {"schema": "public"},
    )

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.tenants.id", ondelete="CASCADE"), nullable=False
    )
    keycloak_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # admin, user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
