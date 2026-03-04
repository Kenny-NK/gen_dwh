"""Flows API endpoints (T059, T060)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_actor_id, get_tenant_db
from src.api.audit_utils import log_audit_event
from src.middleware.auth import get_current_user
from src.services.flow_service import FlowService

router = APIRouter(prefix="/flows", tags=["flows"])


# --- Schemas ---

class FlowCreate(BaseModel):
    name: str = Field(..., max_length=255)
    source_id: UUID
    target_schema: str = Field(..., max_length=63)
    description: str | None = None
    target_table_prefix: str | None = None
    write_mode: str = "append"
    upsert_key: str | None = None


class FlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target_schema: str | None = None
    target_table_prefix: str | None = None
    write_mode: str | None = None
    upsert_key: str | None = None


class FlowTableCreate(BaseModel):
    source_schema: str = Field(..., max_length=255)
    source_table: str = Field(..., max_length=255)
    target_table: str | None = None
    replication_method: str = "FULL_TABLE"
    replication_key: str | None = None
    selected_columns: list[str] | None = None


class FlowTableUpdate(BaseModel):
    target_table: str | None = None
    replication_method: str | None = None
    replication_key: str | None = None
    selected_columns: list[str] | None = None
    sensitive_columns: dict[str, str] | None = None


class FlowResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    source_id: UUID
    target_schema: str
    target_table_prefix: str | None
    status: str
    status_reason: str | None
    write_mode: str
    upsert_key: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FlowTableResponse(BaseModel):
    id: UUID
    flow_id: UUID
    source_schema: str
    source_table: str
    target_table: str
    replication_method: str
    replication_key: str | None
    selected_columns: list[str] | None
    sensitive_columns: dict[str, str] | None
    last_cursor_value: str | None

    model_config = {"from_attributes": True}


# --- Endpoints ---

@router.get("")
async def list_flows(
    status_filter: str | None = Query(None, alias="status"),
    source_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[FlowResponse]:
    service = FlowService(db)
    flows = await service.list_flows(
        status=status_filter,
        source_id=source_id,
        limit=limit,
        offset=offset,
    )
    return [FlowResponse.model_validate(f) for f in flows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_flow(
    body: FlowCreate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> FlowResponse:
    service = FlowService(db)
    try:
        flow = await service.create_flow(
            name=body.name,
            source_id=body.source_id,
            target_schema=body.target_schema,
            write_mode=body.write_mode,
            description=body.description,
            target_table_prefix=body.target_table_prefix,
            upsert_key=body.upsert_key,
            created_by=actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await log_audit_event(
        db=db,
        request=request,
        action="create",
        entity_type="flow",
        entity_id=flow.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes={"name": flow.name, "source_id": str(flow.source_id), "write_mode": flow.write_mode},
    )
    return FlowResponse.model_validate(flow)


@router.get("/{flow_id}")
async def get_flow(
    flow_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> FlowResponse:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    return FlowResponse.model_validate(flow)


@router.patch("/{flow_id}")
async def update_flow(
    flow_id: UUID,
    body: FlowUpdate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> FlowResponse:
    service = FlowService(db)
    updates = body.model_dump(exclude_unset=True)
    flow = await service.update_flow(flow_id, **updates)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    await log_audit_event(
        db=db,
        request=request,
        action="update",
        entity_type="flow",
        entity_id=flow.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes=updates,
    )
    return FlowResponse.model_validate(flow)


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(
    flow_id: UUID,
    request: Request,
    drop_target_tables: bool = Query(False, description="Удалить целевые таблицы в business DB"),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> None:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status == "running":
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалить поток во время выполнения. Сначала дождитесь завершения или отмените запуск.",
        )
    try:
        deleted = await service.delete_flow(flow_id, drop_target_tables=drop_target_tables)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="Поток не найден")
    await log_audit_event(
        db=db,
        request=request,
        action="delete",
        entity_type="flow",
        entity_id=flow_id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes={"drop_target_tables": drop_target_tables},
    )


@router.post("/{flow_id}/activate")
async def activate_flow(
    flow_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> FlowResponse:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Поток нельзя активировать из статуса '{flow.status}'",
        )
    updated = await service.activate_flow(flow_id)
    if not updated:
        raise HTTPException(status_code=400, detail="Не удалось активировать поток")
    await log_audit_event(
        db=db,
        request=request,
        action="activate",
        entity_type="flow",
        entity_id=updated.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
    )
    return FlowResponse.model_validate(updated)


@router.post("/{flow_id}/pause")
async def pause_flow(
    flow_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> FlowResponse:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status in ("running",):
        raise HTTPException(status_code=400, detail="Нельзя поставить на паузу выполняющийся поток")
    flow = await service.update_flow(flow_id, status="paused")
    await log_audit_event(
        db=db,
        request=request,
        action="pause",
        entity_type="flow",
        entity_id=flow.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
    )
    return FlowResponse.model_validate(flow)


# --- Flow Tables ---

@router.get("/{flow_id}/tables")
async def list_flow_tables(
    flow_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[FlowTableResponse]:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    return [FlowTableResponse.model_validate(t) for t in flow.tables]


@router.post("/{flow_id}/tables", status_code=status.HTTP_201_CREATED)
async def add_flow_table(
    flow_id: UUID,
    body: FlowTableCreate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> FlowTableResponse:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    try:
        table = await service.add_table(
            flow_id=flow_id,
            source_schema=body.source_schema,
            source_table=body.source_table,
            target_table=body.target_table,
            replication_method=body.replication_method,
            replication_key=body.replication_key,
            selected_columns=body.selected_columns,
        )
    except ValueError as exc:
        message = str(exc)
        if "уже добавлена" in message.lower():
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=400, detail=message)
    await log_audit_event(
        db=db,
        request=request,
        action="add_table",
        entity_type="flow",
        entity_id=flow_id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes={"source_schema": body.source_schema, "source_table": body.source_table},
    )
    return FlowTableResponse.model_validate(table)


@router.patch("/{flow_id}/tables/{table_id}")
async def update_flow_table(
    flow_id: UUID,
    table_id: UUID,
    body: FlowTableUpdate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> FlowTableResponse:
    service = FlowService(db)
    updates = body.model_dump(exclude_unset=True)
    table = await service.update_table(table_id, flow_id=flow_id, **updates)
    if not table:
        raise HTTPException(status_code=404, detail="Таблица не найдена")
    await log_audit_event(
        db=db,
        request=request,
        action="update_table",
        entity_type="flow",
        entity_id=flow_id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes=updates,
    )
    return FlowTableResponse.model_validate(table)


@router.delete("/{flow_id}/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_flow_table(
    flow_id: UUID,
    table_id: UUID,
    request: Request,
    drop_target_table: bool = Query(False, description="Удалить целевую таблицу в business DB"),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> None:
    service = FlowService(db)
    flow = await service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if flow.status == "running":
        raise HTTPException(
            status_code=400,
            detail="Нельзя удалять таблицы из потока во время выполнения.",
        )
    try:
        removed = await service.remove_table(
            table_id,
            flow_id=flow_id,
            drop_target_table=drop_target_table,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not removed:
        raise HTTPException(status_code=404, detail="Таблица не найдена")
    await log_audit_event(
        db=db,
        request=request,
        action="remove_table",
        entity_type="flow",
        entity_id=flow_id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes={"table_id": str(table_id), "drop_target_table": drop_target_table},
    )
