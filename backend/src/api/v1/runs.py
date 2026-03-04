"""Runs API endpoints (T081, T085, T086)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_utils import log_audit_event
from src.api.deps import get_current_actor_id, get_tenant_db
from src.core.tenant import get_current_tenant_schema
from src.middleware.auth import get_current_user
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


@router.get("/flows/{flow_id}/runs")
async def list_flow_runs(
    flow_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[RunResponse]:
    flow = await FlowService(db).get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    service = RunService(db)
    runs = await service.list_runs(flow_id=flow_id, status=status_filter, limit=limit, offset=offset)
    return [RunResponse.model_validate(r) for r in runs]


@router.post("/flows/{flow_id}/runs", status_code=status.HTTP_201_CREATED)
async def trigger_run(
    flow_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    """Trigger a manual run (T085)."""
    flow = await FlowService(db).get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status == "draft":
        raise HTTPException(status_code=400, detail="Сначала активируйте поток")
    if not flow.tables:
        raise HTTPException(status_code=400, detail="В потоке нет таблиц для запуска")
    if not flow.source or flow.source.connection_status == "invalid":
        raise HTTPException(status_code=400, detail="Источник недоступен. Проверьте подключение")

    service = RunService(db)

    # Check for active runs
    if await service.has_active_run(flow_id):
        raise HTTPException(status_code=409, detail="Запуск этого потока уже выполняется")

    try:
        run = await service.create_run(flow_id, triggered_by="manual")
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Поток не найден")
        raise HTTPException(status_code=409, detail="Не удалось создать запуск. Повторите попытку.")

    # Dispatch Celery task
    tenant_schema = get_current_tenant_schema()
    if not tenant_schema:
        raise HTTPException(status_code=500, detail="Не определена схема арендатора")
    try:
        execute_flow_run.delay(str(run.id), str(flow_id), tenant_schema)
    except Exception:
        run.status = "failed"
        run.error_message = "Не удалось отправить запуск в очередь выполнения"
        run.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить запуск в очередь. Проверьте Redis/Celery.",
        )

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
    return RunResponse.model_validate(run)


@router.get("/flows/{flow_id}/runs/{run_id}")
async def get_run(
    flow_id: UUID,
    run_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
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
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    """Cancel a running task (T086)."""
    service = RunService(db)
    run = await service.cancel_run(run_id, flow_id=flow_id)
    if not run:
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
    return RunResponse.model_validate(run)


@router.post("/flows/{flow_id}/runs/{run_id}/retry")
async def retry_run(
    flow_id: UUID,
    run_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> RunResponse:
    """Retry a failed run."""
    flow = await FlowService(db).get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")

    service = RunService(db)
    old_run = await service.get_run_for_flow(run_id, flow_id)
    if not old_run or old_run.status != "failed":
        raise HTTPException(status_code=400, detail="Повтор возможен только для завершившихся с ошибкой запусков")

    try:
        run = await service.create_run(flow_id, triggered_by="retry")
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail="Поток не найден")
        raise HTTPException(status_code=409, detail="Не удалось создать повторный запуск. Повторите попытку.")
    tenant_schema = get_current_tenant_schema()
    if not tenant_schema:
        raise HTTPException(status_code=500, detail="Не определена схема арендатора")
    try:
        execute_flow_run.delay(str(run.id), str(flow_id), tenant_schema)
    except Exception:
        run.status = "failed"
        run.error_message = "Не удалось отправить повторный запуск в очередь выполнения"
        run.completed_at = datetime.now(UTC)
        await db.commit()
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить повторный запуск в очередь. Проверьте Redis/Celery.",
        )
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
    return RunResponse.model_validate(run)


@router.get("/runs/{run_id}")
async def get_run_by_id(
    run_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
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
    current_user: dict = Depends(get_current_user),
) -> list[RunResponse]:
    service = RunService(db)
    runs = await service.list_runs(status=status_filter, limit=limit, offset=offset)
    return [RunResponse.model_validate(r) for r in runs]
