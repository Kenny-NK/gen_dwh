"""Notifications API endpoints (T103)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_actor_id, get_tenant_db
from src.middleware.auth import get_current_user
from src.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    is_read: bool
    related_entity_type: str | None
    related_entity_id: UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("")
async def list_notifications(
    unread_only: bool = Query(False),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> list[NotificationResponse]:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    notifications = await service.list_notifications(actor_id, unread_only=unread_only)
    return [NotificationResponse.model_validate(n) for n in notifications]


@router.get("/count")
async def unread_count(
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    count = await service.unread_count(actor_id)
    return {"unread_count": count}


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    updated = await service.mark_read(notification_id, actor_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Уведомление не найдено")
    return {"status": "ok"}


@router.post("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    await service.mark_all_read(actor_id)
    return {"status": "ok"}
