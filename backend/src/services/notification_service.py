"""Notification service (T100, T106)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_notification(
        self,
        type: str,
        title: str,
        message: str,
        user_id: UUID | None = None,
        is_broadcast: bool = False,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            is_broadcast=is_broadcast,
            type=type,
            title=title,
            message=message,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        self.session.add(notification)
        await self.session.flush()
        await self.session.commit()
        return notification

    async def list_notifications(
        self, user_id: UUID, unread_only: bool = False, limit: int = 50
    ) -> list[Notification]:
        query = select(Notification).where(
            (Notification.user_id == user_id) | (Notification.is_broadcast.is_(True))
        )
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        query = query.order_by(Notification.created_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_read(self, notification_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                (Notification.user_id == user_id) | (Notification.is_broadcast.is_(True)),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        await self.session.commit()
        return bool(result.rowcount)

    async def mark_all_read(self, user_id: UUID) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                (Notification.user_id == user_id) | (Notification.is_broadcast.is_(True)),
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        await self.session.commit()

    async def unread_count(self, user_id: UUID) -> int:
        from sqlalchemy import func

        result = await self.session.execute(
            select(func.count(Notification.id)).where(
                (Notification.user_id == user_id) | (Notification.is_broadcast.is_(True)),
                Notification.is_read.is_(False),
            )
        )
        return result.scalar() or 0
