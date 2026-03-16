"""Jira-specific source endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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
from src.core.config import settings
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.schemas.jira import JiraExtractionConfig, JiraProject, JiraStreamMetadata
from src.services.connection import decrypt_password
from src.services.jira_service import JiraService
from src.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["Jira"])


class JiraPreviewRequest(BaseModel):
    streams: list[str] | None = None
    project_keys: list[str] | None = None
    jql: str | None = None
    query_mode: str | None = None
    start_date: datetime | None = None
    batch_size: int | None = Field(default=None, ge=1, le=1000)

    model_config = {
        "json_schema_extra": {
            "example": {
                "streams": ["issues", "worklogs"],
                "project_keys": ["DWH", "BI"],
                "query_mode": "basic",
                "start_date": "2026-01-01T00:00:00Z",
                "batch_size": 100,
            }
        }
    }


class JiraProjectsResponse(BaseModel):
    projects: list[JiraProject]
    total_count: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "projects": [
                    {
                        "id": "10001",
                        "key": "DWH",
                        "name": "Data Warehouse",
                        "lead_display_name": "Ivan Petrov",
                        "lead_account_id": "5b10a2844c20165700ede21g",
                    }
                ],
                "total_count": 1,
            }
        }
    }


class JiraStreamsResponse(BaseModel):
    streams: list[JiraStreamMetadata]
    total_count: int


class JiraStreamSchemaResponse(BaseModel):
    stream_name: str
    schema: dict[str, Any]
    field_count: int
    replication_key: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "stream_name": "issues",
                "schema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "key": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
                "field_count": 45,
                "replication_key": "updated",
            }
        }
    }


class JiraExtractionConfigResponse(BaseModel):
    source_id: str
    extraction_config: dict[str, Any]

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_id": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
                "extraction_config": {
                    "auth_type": "basic_token",
                    "query_mode": "basic",
                    "streams": ["issues", "worklogs"],
                    "project_keys": ["DWH"],
                    "batch_size": 100,
                    "incremental_enabled": True,
                    "replication_key": "updated",
                    "runtime_engine": "native",
                },
            }
        }
    }


class JiraPreviewResponse(BaseModel):
    success: bool
    streams: list[str]
    records: dict[str, list[dict[str, Any]]]
    schema: dict[str, Any]
    record_count: int
    effective_query_mode: str | None = None
    effective_jql: str | None = None
    columns_by_stream: dict[str, list[str]] = Field(default_factory=dict)
    rows_by_stream: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    schema_by_stream: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "streams": ["issues"],
                "records": {
                    "issues": [
                        {
                            "id": "10000",
                            "key": "DWH-1",
                            "summary": "Broken sync",
                        }
                    ]
                },
                "schema": {"issues": {"type": "object"}},
                "record_count": 1,
                "effective_query_mode": "basic",
                "effective_jql": "project in (DWH) ORDER BY updated DESC",
                "columns_by_stream": {"issues": ["id", "key", "summary"]},
                "rows_by_stream": {
                    "issues": [
                        {
                            "id": "10000",
                            "key": "DWH-1",
                            "summary": "Broken sync",
                        }
                    ]
                },
                "schema_by_stream": {"issues": {"type": "object"}},
            }
        }
    }


async def _resolve_jira_credentials(
    source_id: UUID,
    db: AsyncSession,
) -> tuple[Any, str, str]:
    if not settings.jira_connector_enabled:
        raise HTTPException(status_code=404, detail="Jira connector is disabled")

    source = await SourceService(db).get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Источник не найден")
    if (source.source_type or "").lower() != "jira":
        raise HTTPException(
            status_code=400,
            detail="This endpoint is only available for Jira sources",
        )
    if not source.credential:
        raise HTTPException(status_code=400, detail="У Jira-источника отсутствует API token")
    token = await decrypt_password(db, source.credential.password_encrypted)
    extraction_config = source.extraction_config if isinstance(source.extraction_config, dict) else {}
    auth_type = str(extraction_config.get("auth_type") or "").strip().lower()
    if auth_type not in {"basic_token", "basic_password", "pat_bearer"}:
        auth_type = "basic_token"
    return source, token, auth_type


@router.get(
    "/{source_id}/jira/projects",
    summary="Получить проекты Jira",
    description="Проверяет доступ к Jira и возвращает список проектов, доступных под указанными credentials.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
) 
async def get_jira_projects(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> JiraProjectsResponse:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    try:
        async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
            projects = await jira.get_projects()
    except Exception as exc:
        classified = JiraService.classify_error(exc)
        raise HTTPException(
            status_code=400,
            detail={
                "message": classified.message,
                "error_type": classified.error_type,
                "suggestion": classified.suggestion,
            },
        ) from exc
    return JiraProjectsResponse(projects=projects, total_count=len(projects))


@router.get(
    "/{source_id}/jira/streams",
    summary="Получить поддерживаемые Jira stream'ы",
    description="Возвращает список stream'ов, которые поддерживает native Jira connector в текущем backend.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
) 
async def get_jira_streams(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> JiraStreamsResponse:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
        streams = jira.get_streams()
    return JiraStreamsResponse(streams=streams, total_count=len(streams))


@router.get(
    "/{source_id}/jira/streams/{stream_name}/schema",
    summary="Получить схему Jira stream'а",
    description="Возвращает JSON schema и метаданные репликации для одного stream'а Jira.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
) 
async def get_jira_stream_schema(
    source_id: UUID,
    stream_name: str,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> JiraStreamSchemaResponse:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
        try:
            return JiraStreamSchemaResponse.model_validate(jira.get_stream_schema(stream_name))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/{source_id}/extraction-config",
    summary="Обновить extraction config Jira",
    description=(
        "Сохраняет extraction config Jira-источника. Backend автоматически нормализует зависимости "
        "между stream'ами, например добавляет `issues`, если он нужен дочерним stream'ам."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
) 
async def update_extraction_config(
    source_id: UUID,
    body: JiraExtractionConfig,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> JiraExtractionConfigResponse:
    service = SourceService(db)
    try:
        source = await service.update_extraction_config(
            source_id=source_id,
            extraction_config=body.model_dump(mode="json"),
            auto_commit=False,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not source:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Источник не найден")
    await db.commit()
    return JiraExtractionConfigResponse(
        source_id=str(source.id),
        extraction_config=source.extraction_config or {},
    )


@router.post(
    "/{source_id}/jira/preview",
    summary="Выполнить preview Jira-данных",
    description=(
        "Запрашивает тестовые записи из Jira по streams и extraction config. Удобен для проверки "
        "прав доступа, JQL и набора возвращаемых полей до создания flow."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
) 
async def jira_preview(
    source_id: UUID,
    body: JiraPreviewRequest,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.PREVIEW_READ)),
    current_user: dict = Depends(get_current_user),
) -> JiraPreviewResponse:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    config = JiraExtractionConfig.model_validate(source.extraction_config or {})
    streams = body.streams or config.streams
    project_keys = body.project_keys if body.project_keys is not None else config.project_keys
    jql = body.jql if body.jql is not None else config.jql
    query_mode = body.query_mode if body.query_mode is not None else config.query_mode
    start_date = body.start_date if body.start_date is not None else config.start_date
    batch_size = body.batch_size if body.batch_size is not None else config.batch_size

    try:
        async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
            preview = await jira.preview_records(
                streams=streams,
                project_keys=project_keys,
                jql=jql,
                query_mode=query_mode,
                batch_size=batch_size,
                start_date=start_date,
            )
    except Exception as exc:
        classified = JiraService.classify_error(exc)
        raise HTTPException(
            status_code=400,
            detail={
                "message": classified.message,
                "error_type": classified.error_type,
                "suggestion": classified.suggestion,
            },
        ) from exc

    return JiraPreviewResponse(
        success=True,
        streams=preview["streams"],
        records=preview["records"],
        schema=preview["schema"],
        record_count=preview["record_count"],
        effective_query_mode=preview.get("effective_query_mode"),
        effective_jql=preview.get("effective_jql"),
        columns_by_stream=preview.get("columns_by_stream", {}),
        rows_by_stream=preview.get("rows_by_stream", {}),
        schema_by_stream=preview.get("schema_by_stream", preview["schema"]),
    )
