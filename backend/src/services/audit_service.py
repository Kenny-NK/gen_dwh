"""Audit service with logging (T101, T102)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditEvent


def _escape_like_pattern(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _apply_filters(
        query,
        *,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        user_email: str | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ):
        if entity_type:
            query = query.where(AuditEvent.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditEvent.entity_id == entity_id)
        if user_id:
            query = query.where(AuditEvent.user_id == user_id)
        if user_email:
            escaped = _escape_like_pattern(user_email.strip().lower())
            query = query.where(
                func.lower(AuditEvent.user_email).like(f"%{escaped}%", escape="\\")
            )
        if action:
            escaped = _escape_like_pattern(action.strip().lower())
            query = query.where(
                func.lower(AuditEvent.action).like(f"%{escaped}%", escape="\\")
            )
        if date_from:
            query = query.where(AuditEvent.created_at >= date_from)
        if date_to:
            query = query.where(AuditEvent.created_at <= date_to)
        return query

    async def log_event(
        self,
        action: str,
        entity_type: str,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        user_email: str | None = None,
        changes: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            user_id=user_id,
            user_email=user_email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_events(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        user_email: str | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        query = select(AuditEvent)
        query = self._apply_filters(
            query,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
        query = query.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count_events(
        self,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        user_id: UUID | None = None,
        user_email: str | None = None,
        action: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        query = select(func.count(AuditEvent.id))
        query = self._apply_filters(
            query,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            user_email=user_email,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
        result = await self.session.execute(query)
        return int(result.scalar() or 0)
