"""SQLAlchemy base model and engine setup."""

from datetime import UTC, datetime
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.config import settings

system_engine = create_async_engine(settings.database_system_url, echo=settings.debug)
business_engine = create_async_engine(settings.database_business_url, echo=settings.debug)

SystemSessionLocal = async_sessionmaker(system_engine, class_=AsyncSession, expire_on_commit=False)
BusinessSessionLocal = async_sessionmaker(
    business_engine, class_=AsyncSession, expire_on_commit=False
)


def now_utc() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_utc,
        server_default=func.now(),
        onupdate=now_utc,
    )
