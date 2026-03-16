"""Audit API endpoints - admin only (T104)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db, require_permission
from src.api.openapi_responses import (
    RESPONSE_400_BAD_REQUEST,
    RESPONSE_401_UNAUTHORIZED,
    RESPONSE_403_FORBIDDEN,
    RESPONSE_422_VALIDATION,
    merge_openapi_responses,
)
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["Audit"])


class AuditEventResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    user_email: str | None
    action: str
    entity_type: str
    entity_id: UUID | None
    changes: dict | None
    ip_address: str | None
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "706f5484-2f76-4ff4-9506-812e0ec4252d",
                "user_id": "1d946a68-5998-40cc-bc61-539a8caeb7ea",
                "user_email": "owner@example.com",
                "action": "create",
                "entity_type": "source",
                "entity_id": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
                "changes": {
                    "name": "Postgres ERP",
                    "host": "erp-db.internal",
                    "database": "erp",
                },
                "ip_address": "127.0.0.1",
                "created_at": "2026-03-12T08:00:00Z",
            }
        },
    }


class AuditListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int


@router.get(
    "",
    summary="Список событий аудита",
    description="Возвращает tenant-scoped аудит с фильтрами по сущности, пользователю, действию и диапазону дат.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def list_audit_events(
    entity_type: str | None = Query(
        None,
        description="Фильтр по типу сущности, например `source`, `flow`, `run` или `schedule`.",
        openapi_examples={"source": {"summary": "Только события источников", "value": "source"}},
    ),
    entity_id: UUID | None = Query(
        None,
        description="UUID конкретной сущности, если нужен аудит только по одному объекту.",
        openapi_examples={
            "source_id": {
                "summary": "События по одному source",
                "value": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
            }
        },
    ),
    user_email: str | None = Query(
        None,
        description="Email пользователя, чьи действия нужно найти в аудите.",
        openapi_examples={
            "owner": {"summary": "Действия владельца workspace", "value": "owner@example.com"}
        },
    ),
    action: str | None = Query(
        None,
        description="Фильтр по действию, например `create`, `update`, `delete`, `trigger_run`.",
        openapi_examples={"create": {"summary": "Только создание", "value": "create"}},
    ),
    date_from: datetime | None = Query(
        None,
        description="Начало диапазона в ISO 8601, например `2026-03-01T00:00:00Z`.",
        openapi_examples={
            "month_start": {
                "summary": "Начало месяца",
                "value": "2026-03-01T00:00:00Z",
            }
        },
    ),
    date_to: datetime | None = Query(
        None,
        description="Конец диапазона в ISO 8601, например `2026-03-12T23:59:59Z`.",
        openapi_examples={
            "today_end": {
                "summary": "Конец текущего дня",
                "value": "2026-03-12T23:59:59Z",
            }
        },
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Максимум событий на страницу.",
        openapi_examples={"page_size": {"summary": "50 событий", "value": 50}},
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Смещение относительно начала выборки для пагинации.",
        openapi_examples={"second_page": {"summary": "Вторая страница", "value": 50}},
    ),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.AUDIT_READ)),
    current_user: dict = Depends(get_current_user),
) -> AuditListResponse:
    service = AuditService(db)
    events = await service.list_events(
        entity_type=entity_type,
        entity_id=entity_id,
        user_email=user_email,
        action=action,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    total = await service.count_events(
        entity_type=entity_type,
        entity_id=entity_id,
        user_email=user_email,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return AuditListResponse(
        items=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
    )
