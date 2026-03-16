"""Notifications API endpoints (T103)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_actor_id, get_tenant_db
from src.api.openapi_responses import (
    RESPONSE_400_BAD_REQUEST,
    RESPONSE_401_UNAUTHORIZED,
    RESPONSE_403_FORBIDDEN,
    RESPONSE_404_NOT_FOUND,
    RESPONSE_422_VALIDATION,
    merge_openapi_responses,
)
from src.middleware.auth import get_current_user
from src.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    title: str
    message: str
    is_read: bool
    related_entity_type: str | None
    related_entity_id: UUID | None
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "fdab31c4-c02b-4d87-8967-e39a55690f85",
                "type": "run_failed",
                "title": "Загрузка завершилась с ошибкой",
                "message": "Flow ERP Orders завершился со статусом failed.",
                "is_read": False,
                "related_entity_type": "run",
                "related_entity_id": "0d0d6d7d-478f-4b3d-b02d-c90f25232a4e",
                "created_at": "2026-03-12T09:15:00Z",
            }
        },
    }


class UnreadCountResponse(BaseModel):
    unread_count: int

    model_config = {"json_schema_extra": {"example": {"unread_count": 3}}}


class NotificationOperationResponse(BaseModel):
    status: str

    model_config = {"json_schema_extra": {"example": {"status": "ok"}}}


@router.get(
    "",
    summary="Список уведомлений",
    description="Возвращает уведомления текущего пользователя в активном workspace.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> list[NotificationResponse]:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    notifications = await service.list_notifications(
        actor_id, unread_only=unread_only, limit=limit, offset=offset
    )
    return [NotificationResponse.model_validate(n) for n in notifications]


@router.get(
    "/count",
    summary="Количество непрочитанных уведомлений",
    description="Короткий endpoint для бейджа уведомлений в интерфейсе.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
    ),
)
async def unread_count(
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> UnreadCountResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    count = await service.unread_count(actor_id)
    return UnreadCountResponse(unread_count=count)


@router.post(
    "/{notification_id}/read",
    summary="Пометить уведомление прочитанным",
    description="Помечает одно уведомление как прочитанное.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def mark_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> NotificationOperationResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    updated = await service.mark_read(notification_id, actor_id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Уведомление не найдено")
    return NotificationOperationResponse(status="ok")


@router.post(
    "/read-all",
    summary="Пометить все уведомления прочитанными",
    description="Отмечает все уведомления пользователя как прочитанные.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
    ),
)
async def mark_all_read(
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> NotificationOperationResponse:
    if not actor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Пользователь не сопоставлен в локальной БД")
    service = NotificationService(db)
    await service.mark_all_read(actor_id)
    return NotificationOperationResponse(status="ok")
