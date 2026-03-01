"""Audit API endpoints - admin only (T104)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db
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


@router.get("")
async def list_audit_events(
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[AuditEventResponse]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")

    service = AuditService(db)
    events = await service.list_events(
        entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset
    )
    return [AuditEventResponse.model_validate(e) for e in events]
