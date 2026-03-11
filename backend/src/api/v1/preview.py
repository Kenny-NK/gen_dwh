"""Preview API endpoints (T061, T062)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db, require_permission
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.services.flow_service import FlowService
from src.services.masking import mask_row
from src.services.preview import PreviewService

router = APIRouter(prefix="/flows/{flow_id}/preview", tags=["preview"])


class PreviewRequest(BaseModel):
    row_limit: int = Field(100, ge=1, le=10000)
    tables: list[str] | None = None
    preview_mode: str | None = Field(default=None, pattern="^(auto|live|snapshot)$")


class PreviewSessionResponse(BaseModel):
    id: UUID
    flow_id: UUID
    status: str
    row_limit: int
    total_rows: int | None
    tables_available: list[str] | None
    requested_mode: str | None
    resolved_mode: str
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
    expires_at: datetime | None

    model_config = {"from_attributes": True}


@router.post("", status_code=202)
async def start_preview(
    flow_id: UUID,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.PREVIEW_READ)),
    current_user: dict = Depends(get_current_user),
) -> PreviewSessionResponse:
    """Start a preview session (T061)."""
    flow_service = FlowService(db)
    flow = await flow_service.get_flow(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Поток не найден")
    if not flow.tables:
        raise HTTPException(
            status_code=400,
            detail="Для предпросмотра сначала добавьте таблицы в поток",
        )

    available_tables = [f"{ft.source_schema}.{ft.source_table}" for ft in flow.tables]
    selected_tables = body.tables or available_tables
    if not selected_tables:
        raise HTTPException(status_code=400, detail="Не выбраны таблицы для предпросмотра")
    unknown = [t for t in selected_tables if t not in available_tables]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Неизвестные таблицы: {', '.join(unknown)}")

    service = PreviewService(db)
    try:
        session = await service.create_session(
            flow_id=flow_id,
            row_limit=body.row_limit,
            tables_available=selected_tables,
            requested_mode=body.preview_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PreviewSessionResponse.model_validate(session)


@router.get("/{session_id}")
async def get_preview_status(
    flow_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.PREVIEW_READ)),
    current_user: dict = Depends(get_current_user),
) -> PreviewSessionResponse:
    """Get preview session status (T061)."""
    service = PreviewService(db)
    session = await service.get_session_for_flow(session_id, flow_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия предпросмотра не найдена")
    return PreviewSessionResponse.model_validate(session)


@router.get("/{session_id}/data")
async def get_preview_data(
    flow_id: UUID,
    session_id: UUID,
    table: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.PREVIEW_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get preview data with masking (T061, T062)."""
    service = PreviewService(db)
    session = await service.get_session_for_flow(session_id, flow_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия предпросмотра не найдена")
    try:
        data = await service.get_preview_data(
            session_id, table, page, page_size, sort_by, sort_order
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Apply masking for non-admin users
    user_permissions = {str(value) for value in current_user.get("permissions", [])}
    if str(Permission.PII_UNMASKED) not in user_permissions:
        # Get sensitive columns from flow table config
        flow_service = FlowService(db)
        flow = await flow_service.get_flow(flow_id)
        if flow:
            for ft in flow.tables:
                full_name = f"{ft.source_schema}.{ft.source_table}"
                if table in {ft.source_table, full_name} and ft.sensitive_columns:
                    data["rows"] = [
                        mask_row(row, ft.sensitive_columns) for row in data["rows"]
                    ]
                    data["masking_applied"] = True
                    break

    return data
