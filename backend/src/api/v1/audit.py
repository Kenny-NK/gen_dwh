"""Audit API endpoints - admin only (T104)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db, require_permission
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


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

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int


@router.get("")
async def list_audit_events(
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    user_email: str | None = None,
    action: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
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
