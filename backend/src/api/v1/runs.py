"""Runs API endpoints (T081, T085, T086)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_utils import log_audit_event
from src.api.deps import get_current_actor_id, get_tenant_db, require_permission
from src.core.permissions import Permission
from src.core.tenant import get_current_tenant_schema
from src.middleware.auth import get_current_user
from src.models.run import Run
from src.services.flow_service import FlowService
from src.services.run_service import RunService
from src.services.scheduler import execute_flow_run

router = APIRouter(tags=["runs"])


class RunResponse(BaseModel):
    id: UUID
    flow_id: UUID
    run_number: int
    triggered_by: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    tables_processed: int
    records_processed: int
    source_records_total: int | None
    source_records_total_is_estimate: bool
    records_failed: int
    error_message: str | None
    retry_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int
    limit: int
    offset: int


async def _set_run_dispatch_state(
    db: AsyncSession,
    run_id: UUID,
    *,
    celery_task_id: str | None = None,
    status_value: str | None = None,
    error_message: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    values: dict[str, object | None] = {}
    if celery_task_id is not None:
        values["celery_task_id"] = celery_task_id
    if status_value is not None:
        values["status"] = status_value
    if error_message is not None:
        values["error_message"] = error_message
    if completed_at is not None:
        values["completed_at"] = completed_at
    if not values:
        return

    await db.execute(update(Run).where(Run.id == run_id).values(**values))
    await db.commit()


@router.get("/flows/{flow_id}/runs")
async def list_flow_runs(
    flow_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.FLOWS_READ)),
    current_user: dict = Depends(get_current_user),
) -> RunListResponse:
    flow = await FlowService(db).get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    service = RunService(db)
    runs = await service.list_runs(flow_id=flow_id, status=status_filter, limit=limit, offset=offset)
    total = await service.count_runs(flow_id=flow_id, status=status_filter)
    return RunListResponse(
        items=[RunResponse.model_validate(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/flows/{flow_id}/runs", status_code=status.HTTP_202_ACCEPTED)
async def trigger_run(
    flow_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.FLOWS_RUN)),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    """Trigger a manual run (T085)."""
    flow = await FlowService(db).get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status == "draft":
        raise HTTPException(status_code=400, detail="Сначала активируйте поток")
    if flow.source_deleted or flow.source_id is None:
        raise HTTPException(
            status_code=400,
            detail="Источник удален. Запуск потока заблокирован до ручного удаления потока.",
        )
    if not flow.tables:
        raise HTTPException(status_code=400, detail="В потоке нет таблиц для запуска")
    if not flow.source or flow.source.connection_status == "invalid":
        raise HTTPException(status_code=400, detail="Источник недоступен. Проверьте подключение")
    service = RunService(db)

    # Check for active runs
    if await service.has_active_run(flow_id):
        raise HTTPException(status_code=409, detail="Запуск этого потока уже выполняется")

    try:
        run = await service.create_run(flow_id, triggered_by="manual", auto_commit=False)
        await log_audit_event(
            db=db,
            request=request,
            action="trigger_run",
            entity_type="run",
            entity_id=run.id,
            user_id=actor_id,
            user_email=current_user.get("email"),
            changes={"flow_id": str(flow_id), "triggered_by": "manual"},
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Поток не найден") from exc
        raise HTTPException(status_code=409, detail="Не удалось создать запуск. Повторите попытку.") from exc
    except Exception:
        await db.rollback()
        raise

    # Dispatch Celery task
    tenant_schema = get_current_tenant_schema()
    if not tenant_schema:
        raise HTTPException(status_code=500, detail="Не определена схема арендатора")
    try:
        task_result = execute_flow_run.delay(str(run.id), str(flow_id), tenant_schema)
        await _set_run_dispatch_state(db, run.id, celery_task_id=task_result.id)
    except Exception:
        await _set_run_dispatch_state(
            db,
            run.id,
            status_value="failed",
            error_message="Не удалось отправить запуск в очередь выполнения",
            completed_at=datetime.now(UTC),
        )
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить запуск в очередь. Проверьте Redis/Celery.",
        )
    run = await service.get_run_for_flow(run.id, flow_id) or run
    return RunResponse.model_validate(run)


@router.get("/flows/{flow_id}/runs/{run_id}")
async def get_run(
    flow_id: UUID,
    run_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.FLOWS_READ)),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    service = RunService(db)
    run = await service.get_run_for_flow(run_id, flow_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return RunResponse.model_validate(run)


@router.post("/flows/{flow_id}/runs/{run_id}/cancel")
async def cancel_run(
    flow_id: UUID,
    run_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.FLOWS_RUN)),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    """Cancel a running task (T086)."""
    service = RunService(db)
    try:
        run = await service.cancel_run(run_id, flow_id=flow_id, auto_commit=False)
        if not run:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Этот запуск нельзя отменить")
        await log_audit_event(
            db=db,
            request=request,
            action="cancel_run",
            entity_type="run",
            entity_id=run.id,
            user_id=actor_id,
            user_email=current_user.get("email"),
        )
        await db.commit()
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise
    return RunResponse.model_validate(run)


@router.post("/flows/{flow_id}/runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_run(
    flow_id: UUID,
    run_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.FLOWS_RUN)),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    """Retry a failed run."""
    flow = await FlowService(db).get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status == "draft":
        raise HTTPException(status_code=400, detail="Сначала активируйте поток")
    if flow.source_deleted or flow.source_id is None:
        raise HTTPException(
            status_code=400,
            detail="Источник удален. Повторный запуск невозможен.",
        )
    if not flow.tables:
        raise HTTPException(status_code=400, detail="В потоке нет таблиц для запуска")
    if not flow.source or flow.source.connection_status == "invalid":
        raise HTTPException(status_code=400, detail="Источник недоступен. Проверьте подключение")
    service = RunService(db)
    old_run = await service.get_run_for_flow(run_id, flow_id)
    if not old_run or old_run.status != "failed":
        raise HTTPException(status_code=400, detail="Повтор возможен только для завершившихся с ошибкой запусков")
    if await service.has_active_run(flow_id):
        raise HTTPException(status_code=409, detail="Запуск этого потока уже выполняется")

    try:
        run = await service.create_run(flow_id, triggered_by="retry", auto_commit=False)
        await log_audit_event(
            db=db,
            request=request,
            action="retry_run",
            entity_type="run",
            entity_id=run.id,
            user_id=actor_id,
            user_email=current_user.get("email"),
            changes={"flow_id": str(flow_id), "triggered_by": "retry"},
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Поток не найден") from exc
        raise HTTPException(
            status_code=409,
            detail="Не удалось создать повторный запуск. Повторите попытку.",
        ) from exc
    except Exception:
        await db.rollback()
        raise
    tenant_schema = get_current_tenant_schema()
    if not tenant_schema:
        raise HTTPException(status_code=500, detail="Не определена схема арендатора")
    try:
        task_result = execute_flow_run.delay(str(run.id), str(flow_id), tenant_schema)
        await _set_run_dispatch_state(db, run.id, celery_task_id=task_result.id)
    except Exception:
        await _set_run_dispatch_state(
            db,
            run.id,
            status_value="failed",
            error_message="Не удалось отправить повторный запуск в очередь выполнения",
            completed_at=datetime.now(UTC),
        )
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить повторный запуск в очередь. Проверьте Redis/Celery.",
        )
    run = await service.get_run_for_flow(run.id, flow_id) or run
    return RunResponse.model_validate(run)


@router.get("/runs/{run_id}")
async def get_run_by_id(
    run_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.FLOWS_READ)),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    service = RunService(db)
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Запуск не найден")
    return RunResponse.model_validate(run)


@router.get("/runs")
async def list_all_runs(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.FLOWS_READ)),
    current_user: dict = Depends(get_current_user),
) -> RunListResponse:
    service = RunService(db)
    runs = await service.list_runs(status=status_filter, limit=limit, offset=offset)
    total = await service.count_runs(status=status_filter)
    return RunListResponse(
        items=[RunResponse.model_validate(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )
