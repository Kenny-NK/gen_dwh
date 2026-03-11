"""Jira-specific source endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db, require_permission
from src.core.config import settings
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.schemas.jira import JiraExtractionConfig
from src.services.connection import decrypt_password
from src.services.jira_service import JiraService
from src.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["jira"])


class JiraPreviewRequest(BaseModel):
    streams: list[str] | None = None
    project_keys: list[str] | None = None
    jql: str | None = None
    batch_size: int | None = Field(default=None, ge=1, le=1000)


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


@router.get("/{source_id}/jira/projects")
async def get_jira_projects(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
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
    return {"projects": [project.model_dump() for project in projects], "total_count": len(projects)}


@router.get("/{source_id}/jira/streams")
async def get_jira_streams(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
        streams = jira.get_streams()
    return {"streams": [stream.model_dump() for stream in streams], "total_count": len(streams)}


@router.get("/{source_id}/jira/streams/{stream_name}/schema")
async def get_jira_stream_schema(
    source_id: UUID,
    stream_name: str,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
        try:
            return jira.get_stream_schema(stream_name)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{source_id}/extraction-config")
async def update_extraction_config(
    source_id: UUID,
    body: JiraExtractionConfig,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> dict:
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
    return {"source_id": str(source.id), "extraction_config": source.extraction_config}


@router.post("/{source_id}/jira/preview")
async def jira_preview(
    source_id: UUID,
    body: JiraPreviewRequest,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.PREVIEW_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    source, token, auth_type = await _resolve_jira_credentials(source_id, db)
    config = JiraExtractionConfig.model_validate(source.extraction_config or {})
    streams = body.streams or config.streams
    project_keys = body.project_keys if body.project_keys is not None else config.project_keys
    jql = body.jql if body.jql is not None else config.jql
    batch_size = body.batch_size if body.batch_size is not None else config.batch_size

    try:
        async with JiraService(source.host, source.username, token, auth_type=auth_type) as jira:
            preview = await jira.preview_records(
                streams=streams,
                project_keys=project_keys,
                jql=jql,
                batch_size=batch_size,
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

    return {
        "success": True,
        "streams": preview["streams"],
        "records": preview["records"],
        "schema": preview["schema"],
        "record_count": preview["record_count"],
    }
