"""Notification service (T100, T106)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, case, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification
from src.models.notification_read import NotificationRead


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _broadcast_read_exists(user_id: UUID):
        return exists(
            select(NotificationRead.id).where(
                NotificationRead.notification_id == Notification.id,
                NotificationRead.user_id == user_id,
            )
        )

    @classmethod
    def _unread_filter(cls, user_id: UUID):
        broadcast_read = cls._broadcast_read_exists(user_id)
        return or_(
            and_(Notification.is_broadcast.is_(True), ~broadcast_read),
            and_(Notification.is_broadcast.is_(False), Notification.is_read.is_(False)),
        )

    async def create_notification(
        self,
        type: str,
        title: str,
        message: str,
        user_id: UUID | None = None,
        is_broadcast: bool = False,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
        auto_commit: bool = True,
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
        if auto_commit:
            await self.session.commit()
        return notification

    async def list_notifications(
        self,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        broadcast_read = self._broadcast_read_exists(user_id)
        is_read_expr = case(
            (Notification.is_broadcast.is_(True), broadcast_read),
            else_=Notification.is_read,
        ).label("is_read")
        query = select(
            Notification.id,
            Notification.type,
            Notification.title,
            Notification.message,
            is_read_expr,
            Notification.related_entity_type,
            Notification.related_entity_id,
            Notification.created_at,
        ).where(
            or_(Notification.user_id == user_id, Notification.is_broadcast.is_(True))
        )
        if unread_only:
            query = query.where(self._unread_filter(user_id))
        query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return [dict(row) for row in result.mappings().all()]

    async def mark_read(
        self,
        notification_id: UUID,
        user_id: UUID,
        *,
        auto_commit: bool = True,
    ) -> bool:
        result = await self.session.execute(
            select(Notification.id, Notification.is_broadcast, Notification.user_id).where(
                Notification.id == notification_id,
                or_(Notification.user_id == user_id, Notification.is_broadcast.is_(True)),
            )
        )
        notification = result.one_or_none()
        if notification is None:
            return False

        now = datetime.now(UTC)
        if bool(notification.is_broadcast):
            await self.session.execute(
                insert(NotificationRead)
                .values(notification_id=notification_id, user_id=user_id, read_at=now)
                .on_conflict_do_update(
                    index_elements=["notification_id", "user_id"],
                    set_={"read_at": now},
                )
            )
        else:
            update_result = await self.session.execute(
                update(Notification)
                .where(
                    Notification.id == notification_id,
                    Notification.user_id == user_id,
                )
                .values(is_read=True, read_at=now)
            )
            if not update_result.rowcount:
                return False

        if auto_commit:
            await self.session.commit()
        return True

    async def mark_all_read(self, user_id: UUID, *, auto_commit: bool = True) -> None:
        now = datetime.now(UTC)
        await self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_broadcast.is_(False),
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=now)
        )
        broadcast_ids_result = await self.session.execute(
            select(Notification.id).where(
                Notification.is_broadcast.is_(True),
                ~self._broadcast_read_exists(user_id),
            )
        )
        broadcast_ids = [row[0] for row in broadcast_ids_result.all()]
        if broadcast_ids:
            await self.session.execute(
                insert(NotificationRead)
                .values(
                    [
                        {
                            "notification_id": notification_id,
                            "user_id": user_id,
                            "read_at": now,
                        }
                        for notification_id in broadcast_ids
                    ]
                )
                .on_conflict_do_update(
                    index_elements=["notification_id", "user_id"],
                    set_={"read_at": now},
                )
            )
        if auto_commit:
            await self.session.commit()

    async def unread_count(self, user_id: UUID) -> int:
        result = await self.session.execute(
            select(func.count(Notification.id)).where(
                or_(Notification.user_id == user_id, Notification.is_broadcast.is_(True)),
                self._unread_filter(user_id),
            )
        )
        return result.scalar() or 0
