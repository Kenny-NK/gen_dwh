"""Schedules API endpoints (T082, T083, T084)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_utils import log_audit_event
from src.api.deps import get_current_actor_id, get_tenant_db, require_permission
from src.api.openapi_responses import (
    RESPONSE_400_BAD_REQUEST,
    RESPONSE_401_UNAUTHORIZED,
    RESPONSE_403_FORBIDDEN,
    RESPONSE_404_NOT_FOUND,
    RESPONSE_422_VALIDATION,
    merge_openapi_responses,
)
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.services.schedule_service import ScheduleService

router = APIRouter(tags=["Schedules"])


class ScheduleConfig(BaseModel):
    schedule_type: Literal["cron", "interval", "manual"]
    cron_expression: str | None = None
    interval_minutes: int | None = Field(None, ge=5, le=10080)
    timezone: str = "Europe/Moscow"
    max_retries: int = Field(5, ge=0, le=10)
    timeout_minutes: int = Field(120, ge=1, le=1440)

    model_config = {
        "json_schema_extra": {
            "example": {
                "schedule_type": "cron",
                "cron_expression": "0 */2 * * *",
                "interval_minutes": None,
                "timezone": "Europe/Moscow",
                "max_retries": 5,
                "timeout_minutes": 120,
            }
        }
    }


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

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "aee9118b-7ed4-4f5f-a56a-a9ff2031b1a0",
                "flow_id": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
                "schedule_type": "cron",
                "cron_expression": "0 */2 * * *",
                "interval_minutes": None,
                "timezone": "Europe/Moscow",
                "max_retries": 5,
                "timeout_minutes": 120,
                "is_active": True,
                "last_run_at": "2026-03-12T06:00:00Z",
                "next_run_at": "2026-03-12T08:00:00Z",
                "created_at": "2026-03-11T10:00:00Z",
                "updated_at": "2026-03-12T06:00:00Z",
            }
        },
    }


class CronValidationRequest(BaseModel):
    cron_expression: str

    model_config = {"json_schema_extra": {"example": {"cron_expression": "0 */2 * * *"}}}


class ScheduleListResponse(BaseModel):
    items: list[ScheduleResponse]


class CronValidationResponse(BaseModel):
    valid: bool
    next_times: list[str] | None = None
    error: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "valid": True,
                "next_times": [
                    "2026-03-12T10:00:00+00:00",
                    "2026-03-12T12:00:00+00:00",
                ],
                "error": None,
            }
        }
    }


def _validate_cron_response(cron_expression: str) -> CronValidationResponse:
    result = ScheduleService.validate_cron(cron_expression)
    if result.get("valid"):
        return CronValidationResponse(valid=True, next_times=result.get("next_times", []))
    return CronValidationResponse(valid=False, error=result.get("error"))


@router.get(
    "/flows/{flow_id}/schedule",
    summary="Получить расписание потока",
    description="Возвращает текущее расписание для конкретного flow.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def get_schedule(
    flow_id: UUID = Path(
        ...,
        description="UUID потока, для которого нужно вернуть расписание.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SCHEDULES_READ)),
    current_user: dict = Depends(get_current_user),
) -> ScheduleResponse:
    service = ScheduleService(db)
    schedule = await service.get_schedule(flow_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не настроено")
    return ScheduleResponse.model_validate(schedule)


@router.put(
    "/flows/{flow_id}/schedule",
    summary="Создать или обновить расписание",
    description=(
        "Создает новое расписание или обновляет существующее. Поддерживаются типы `cron`, "
        "`interval` и `manual`."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def upsert_schedule(
    body: ScheduleConfig,
    request: Request,
    flow_id: UUID = Path(
        ...,
        description="UUID потока, для которого создается или обновляется расписание.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SCHEDULES_WRITE)),
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
            auto_commit=False,
        )
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
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise
    return ScheduleResponse.model_validate(schedule)


@router.delete(
    "/flows/{flow_id}/schedule",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить расписание потока",
    description="Удаляет расписание для выбранного flow.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def delete_schedule(
    request: Request,
    flow_id: UUID = Path(
        ...,
        description="UUID потока, у которого нужно удалить расписание.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SCHEDULES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> None:
    service = ScheduleService(db)
    schedule = await service.get_schedule(flow_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Расписание не настроено")
    deleted = await service.delete_schedule(flow_id, auto_commit=False)
    if not deleted:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Не удалось удалить расписание")
    try:
        await log_audit_event(
            db=db,
            request=request,
            action="delete_schedule",
            entity_type="schedule",
            entity_id=schedule.id,
            user_id=actor_id,
            user_email=current_user.get("email"),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@router.post(
    "/flows/{flow_id}/schedule/validate",
    summary="Проверить cron для потока",
    description="Валидирует cron-выражение и показывает ближайшие даты запуска.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def validate_cron(
    body: CronValidationRequest,
    flow_id: UUID = Path(
        ...,
        description="UUID потока, в контексте которого проверяется cron-выражение.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
    _: None = Depends(require_permission(Permission.SCHEDULES_READ)),
    current_user: dict = Depends(get_current_user),
) -> CronValidationResponse:
    return _validate_cron_response(body.cron_expression)


@router.post(
    "/schedules/validate",
    summary="Проверить cron-выражение",
    description="Standalone endpoint для быстрой проверки cron без привязки к flow.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def validate_cron_standalone(
    body: CronValidationRequest,
    _: None = Depends(require_permission(Permission.SCHEDULES_READ)),
    current_user: dict = Depends(get_current_user),
) -> CronValidationResponse:
    return _validate_cron_response(body.cron_expression)


@router.get(
    "/schedules",
    summary="Список расписаний workspace",
    description="Возвращает список расписаний текущего workspace с пагинацией.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def list_schedules(
    is_active: bool | None = Query(
        None,
        description="Фильтр по активности расписания: `true` только активные, `false` только отключенные.",
        openapi_examples={"active_only": {"summary": "Только активные", "value": True}},
    ),
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Количество расписаний на страницу.",
        openapi_examples={"page_size": {"summary": "50 расписаний", "value": 50}},
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Смещение для пагинации по списку расписаний.",
        openapi_examples={"second_page": {"summary": "Вторая страница", "value": 50}},
    ),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SCHEDULES_READ)),
    current_user: dict = Depends(get_current_user),
) -> ScheduleListResponse:
    service = ScheduleService(db)
    schedules = await service.list_schedules(is_active=is_active, limit=limit, offset=offset)
    return ScheduleListResponse(items=[ScheduleResponse.model_validate(s) for s in schedules])
