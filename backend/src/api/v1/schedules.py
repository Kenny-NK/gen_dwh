"""Schedules API endpoints (T082, T083, T084)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_actor_id, get_tenant_db
from src.api.audit_utils import log_audit_event
from src.middleware.auth import get_current_user
from src.services.schedule_service import ScheduleService

router = APIRouter(tags=["schedules"])


class ScheduleConfig(BaseModel):
    schedule_type: Literal["cron", "interval", "manual"]
    cron_expression: str | None = None
    interval_minutes: int | None = Field(None, ge=5, le=10080)
    timezone: str = "Europe/Moscow"
    max_retries: int = Field(5, ge=0, le=10)
    timeout_minutes: int = Field(120, ge=1, le=1440)


class ScheduleResponse(BaseModel):
    id: UUID
    flow_id: UUID
    schedule_type: str
    cron_expression: str | None
    interval_minutes: int | None
    timezone: str
    max_retries: int
    timeout_minutes: int
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CronValidationRequest(BaseModel):
    cron_expression: str


@router.get("/flows/{flow_id}/schedule")
async def get_schedule(
    flow_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> ScheduleResponse:
    service = ScheduleService(db)
    schedule = await service.get_schedule(flow_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не настроено")
    return ScheduleResponse.model_validate(schedule)


@router.put("/flows/{flow_id}/schedule")
async def upsert_schedule(
    flow_id: UUID,
    body: ScheduleConfig,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> ScheduleResponse:
    service = ScheduleService(db)

    if body.schedule_type == "cron" and body.cron_expression:
        validation = ScheduleService.validate_cron(body.cron_expression)
        if not validation["valid"]:
            raise HTTPException(status_code=400, detail=f"Некорректный cron: {validation['error']}")

    try:
        schedule = await service.upsert_schedule(
            flow_id=flow_id,
            schedule_type=body.schedule_type,
            cron_expression=body.cron_expression,
            interval_minutes=body.interval_minutes,
            timezone=body.timezone,
            max_retries=body.max_retries,
            timeout_minutes=body.timeout_minutes,
            created_by=actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await log_audit_event(
        db=db,
        request=request,
        action="upsert_schedule",
        entity_type="schedule",
        entity_id=schedule.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes={
            "flow_id": str(flow_id),
            "schedule_type": body.schedule_type,
            "cron_expression": body.cron_expression,
            "interval_minutes": body.interval_minutes,
            "timezone": body.timezone,
        },
    )
    return ScheduleResponse.model_validate(schedule)


@router.delete("/flows/{flow_id}/schedule", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    flow_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> None:
    service = ScheduleService(db)
    schedule = await service.get_schedule(flow_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не настроено")
    deleted = await service.delete_schedule(flow_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Не удалось удалить расписание")
    await log_audit_event(
        db=db,
        request=request,
        action="delete_schedule",
        entity_type="schedule",
        entity_id=schedule.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
    )


@router.post("/flows/{flow_id}/schedule/validate")
async def validate_cron(
    flow_id: UUID,
    body: CronValidationRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    return ScheduleService.validate_cron(body.cron_expression)


@router.get("/schedules")
async def list_schedules(
    is_active: bool | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[ScheduleResponse]:
    service = ScheduleService(db)
    schedules = await service.list_schedules(is_active=is_active, limit=limit, offset=offset)
    return [ScheduleResponse.model_validate(s) for s in schedules]
