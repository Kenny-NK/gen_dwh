"""Audit service with logging (T101, T102)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit import AuditEvent


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

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
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditEvent]:
        query = select(AuditEvent)
        if entity_type:
            query = query.where(AuditEvent.entity_type == entity_type)
        if entity_id:
            query = query.where(AuditEvent.entity_id == entity_id)
        if user_id:
            query = query.where(AuditEvent.user_id == user_id)
        query = query.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())
