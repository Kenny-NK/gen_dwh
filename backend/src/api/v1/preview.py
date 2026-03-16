"""Preview API endpoints (T061, T062)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db, require_permission
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
from src.services.flow_service import FlowService
from src.services.masking import mask_row
from src.services.preview import PreviewService

router = APIRouter(prefix="/flows/{flow_id}/preview", tags=["Preview"])


class PreviewRequest(BaseModel):
    row_limit: int = Field(100, ge=1, le=10000)
    tables: list[str] | None = None
    preview_mode: str | None = Field(default=None, pattern="^(auto|live|snapshot)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "row_limit": 200,
                "tables": ["public.orders"],
                "preview_mode": "snapshot",
            }
        }
    }


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

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "4d0fa755-faa0-4ea3-a84f-acd86244dc5a",
                "flow_id": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
                "status": "completed",
                "row_limit": 200,
                "total_rows": 128,
                "tables_available": ["public.orders"],
                "requested_mode": "snapshot",
                "resolved_mode": "snapshot",
                "error_message": None,
                "created_at": "2026-03-12T09:00:00Z",
                "completed_at": "2026-03-12T09:00:03Z",
                "expires_at": "2026-03-12T11:00:00Z",
            }
        },
    }


class PreviewDataResponse(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    total: int = 0
    page: int | None = None
    page_size: int | None = None
    total_pages: int | None = None
    masking_applied: bool | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "columns": ["id", "customer_id", "status", "updated_at"],
                "rows": [
                    {
                        "id": 1,
                        "customer_id": 42,
                        "status": "paid",
                        "updated_at": "2026-03-12T09:00:00Z",
                    }
                ],
                "total": 128,
                "page": 1,
                "page_size": 100,
                "total_pages": 2,
                "masking_applied": False,
            }
        }
    }


@router.post(
    "",
    status_code=202,
    summary="Запустить preview потока",
    description=(
        "Создает preview session для выбранного flow и набора таблиц. "
        "Используйте этот endpoint перед `GET /data`, чтобы получить session_id."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def start_preview(
    body: PreviewRequest,
    flow_id: UUID = Path(
        ...,
        description="UUID потока, для которого запускается preview.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
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


@router.get(
    "/{session_id}",
    summary="Получить статус preview session",
    description="Возвращает статус preview session и выбранный режим preview.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def get_preview_status(
    flow_id: UUID = Path(
        ...,
        description="UUID потока, которому принадлежит preview session.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
    session_id: UUID = Path(
        ...,
        description="UUID preview session, полученный при запуске preview.",
        openapi_examples={
            "snapshot_session": {
                "summary": "Snapshot preview session",
                "value": "4d0fa755-faa0-4ea3-a84f-acd86244dc5a",
            }
        },
    ),
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


@router.get(
    "/{session_id}/data",
    summary="Получить данные preview",
    description=(
        "Возвращает страницу preview-данных по конкретной таблице. "
        "Если у пользователя нет права `pii:unmasked`, backend автоматически маскирует чувствительные поля."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def get_preview_data(
    flow_id: UUID = Path(
        ...,
        description="UUID потока, которому принадлежит preview session.",
        openapi_examples={
            "orders_flow": {
                "summary": "Flow для ERP-заказов",
                "value": "85caa7da-bde8-4b7c-a3d5-a90501c8a273",
            }
        },
    ),
    session_id: UUID = Path(
        ...,
        description="UUID preview session, созданной через `POST /flows/{flow_id}/preview`.",
        openapi_examples={
            "snapshot_session": {
                "summary": "Snapshot preview session",
                "value": "4d0fa755-faa0-4ea3-a84f-acd86244dc5a",
            }
        },
    ),
    table: str = Query(
        ...,
        description="Таблица из preview session, для которой нужно вернуть данные.",
        openapi_examples={
            "orders_table": {
                "summary": "Таблица заказов",
                "value": "public.orders",
            }
        },
    ),
    page: int = Query(
        1,
        ge=1,
        description="Номер страницы preview-данных, начиная с 1.",
        openapi_examples={"first_page": {"summary": "Первая страница", "value": 1}},
    ),
    page_size: int = Query(
        100,
        ge=1,
        le=100,
        description="Размер страницы. Для preview ограничен 100 строками.",
        openapi_examples={"compact_page": {"summary": "50 строк", "value": 50}},
    ),
    sort_by: str | None = Query(
        None,
        description="Имя колонки для сортировки результата preview.",
        openapi_examples={
            "updated_at": {"summary": "Сортировка по времени обновления", "value": "updated_at"}
        },
    ),
    sort_order: str = Query(
        "asc",
        pattern="^(asc|desc)$",
        description="Направление сортировки для `sort_by`.",
        openapi_examples={"descending": {"summary": "По убыванию", "value": "desc"}},
    ),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.PREVIEW_READ)),
    current_user: dict = Depends(get_current_user),
) -> PreviewDataResponse:
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

    return PreviewDataResponse.model_validate(data)
