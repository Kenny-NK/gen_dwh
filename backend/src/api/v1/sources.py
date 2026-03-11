"""Sources API endpoints (T041-T044)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_utils import log_audit_event
from src.api.deps import get_current_actor_id, get_system_db, get_tenant_db, require_permission
from src.core.config import settings
from src.core.permissions import Permission
from src.middleware.auth import get_current_user
from src.models.source_credential import SourceCredential
from src.services.connection import decrypt_password, discover_s3_objects, discover_schemas, discover_tables
from src.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])


# --- Schemas ---

class SourceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    source_type: Literal["postgres", "s3", "jira"] = "postgres"
    jira_auth_type: Literal["basic_token", "basic_password", "pat_bearer"] | None = None
    host: str = Field(..., max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field("", max_length=255)
    username: str = Field(..., max_length=255)
    password: str
    description: str | None = None


class SourceUpdate(BaseModel):
    name: str | None = None
    source_type: Literal["postgres", "s3", "jira"] | None = None
    jira_auth_type: Literal["basic_token", "basic_password", "pat_bearer"] | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    description: str | None = None


class SourceConnectionTestRequest(BaseModel):
    source_type: Literal["postgres", "s3", "jira"] = "postgres"
    jira_auth_type: Literal["basic_token", "basic_password", "pat_bearer"] | None = None
    host: str = Field(..., max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field("", max_length=255)
    username: str = Field(..., max_length=255)
    password: str


class SourceResponse(BaseModel):
    id: UUID
    name: str
    source_type: str
    description: str | None
    host: str
    port: int
    database: str
    username: str
    connection_status: str
    last_validated_at: datetime | None
    validation_error: str | None
    extraction_config: dict | None = None
    jira_auth_type: Literal["basic_token", "basic_password", "pat_bearer"] | None = None
    jira_runtime_engine: Literal["meltano", "native"] | None = None
    token_mask: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int


async def _mask_token(source, db: AsyncSession) -> str | None:
    if str(source.source_type or "").lower() != "jira":
        return None
    credential_result = await db.execute(
        select(SourceCredential.password_encrypted).where(SourceCredential.source_id == source.id)
    )
    encrypted_password = credential_result.scalar_one_or_none()
    if not encrypted_password:
        return None
    try:
        token = await decrypt_password(db, encrypted_password)
    except Exception:
        return "****"
    tail = token[-4:] if len(token) >= 4 else token
    return f"{'*' * max(0, len(token) - len(tail))}{tail}"


async def _to_source_response(source, db: AsyncSession) -> SourceResponse:
    payload = SourceResponse.model_validate(source).model_dump()
    if str(source.source_type or "").lower() == "jira":
        extraction_config = source.extraction_config if isinstance(source.extraction_config, dict) else {}
        auth_type = str(extraction_config.get("auth_type") or "").strip().lower()
        if auth_type == "pat_bearer":
            payload["jira_auth_type"] = "pat_bearer"
        elif auth_type == "basic_password":
            payload["jira_auth_type"] = "basic_password"
        else:
            payload["jira_auth_type"] = "basic_token"
        payload["jira_runtime_engine"] = (
            "native" if payload["jira_auth_type"] == "pat_bearer" else "meltano"
        )
    payload["token_mask"] = await _mask_token(source, db)
    return SourceResponse.model_validate(payload)


# --- Endpoints ---

@router.get("")
async def list_sources(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> SourceListResponse:
    """List all sources (T041)."""
    service = SourceService(db)
    sources = await service.list_sources(status=status_filter, limit=limit, offset=offset)
    total = await service.count_sources(status=status_filter)
    items: list[SourceResponse] = []
    for source in sources:
        items.append(await _to_source_response(source, db))
    return SourceListResponse(
        items=items,
        total=total,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> SourceResponse:
    """Create a new source connection (T041)."""
    service = SourceService(db)
    try:
        source = await service.create_source(
            name=body.name,
            source_type=body.source_type,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
            jira_auth_type=body.jira_auth_type,
            description=body.description,
            created_by=actor_id,
            auto_commit=False,
        )
        await log_audit_event(
            db=db,
            request=request,
            action="create",
            entity_type="source",
            entity_id=source.id,
            user_id=actor_id,
            user_email=current_user.get("email"),
            changes={"name": source.name, "host": source.host, "database": source.database},
        )
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise
    return await _to_source_response(source, db)


@router.post("/test-connection")
async def test_source_connection_payload(
    body: SourceConnectionTestRequest,
    db: AsyncSession = Depends(get_system_db),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    service = SourceService(db)
    try:
        return await service.test_connection_payload(
            source_type=body.source_type,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
            jira_auth_type=body.jira_auth_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{source_id}")
async def get_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> SourceResponse:
    """Get source details (T041)."""
    service = SourceService(db)
    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Источник не найден")
    return await _to_source_response(source, db)


@router.patch("/{source_id}")
async def update_source(
    source_id: UUID,
    body: SourceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> SourceResponse:
    """Update source configuration (T041)."""
    service = SourceService(db)
    updates = body.model_dump(exclude_unset=True)
    audit_changes = dict(updates)
    if "password" in audit_changes:
        audit_changes["password"] = "[REDACTED]"
        audit_changes["credentials_updated"] = True
    try:
        source = await service.update_source(source_id, auto_commit=False, **updates)
        if not source:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Источник не найден")
        await log_audit_event(
            db=db,
            request=request,
            action="update",
            entity_type="source",
            entity_id=source.id,
            user_id=actor_id,
            user_email=current_user.get("email"),
            changes=audit_changes,
        )
        await db.commit()
    except HTTPException:
        raise
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise
    return await _to_source_response(source, db)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    request: Request,
    hard_delete: bool = Query(False, description="Полностью удалить источник и credential без возможности восстановления"),
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Delete a source via soft or hard delete (T041)."""
    service = SourceService(db)
    try:
        deleted = await service.delete_source(
            source_id,
            hard_delete=hard_delete,
            auto_commit=False,
        )
        if not deleted:
            await db.rollback()
            raise HTTPException(status_code=404, detail="Источник не найден")
        await log_audit_event(
            db=db,
            request=request,
            action="delete",
            entity_type="source",
            entity_id=source_id,
            user_id=actor_id,
            user_email=current_user.get("email"),
            changes={"hard_delete": hard_delete},
        )
        await db.commit()
    except HTTPException:
        raise
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await db.rollback()
        raise


@router.post("/{source_id}/test")
async def test_source_connection(
    source_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Test source connection (T042)."""
    service = SourceService(db)
    try:
        result = await service.test_source_connection(source_id, auto_commit=False)
        await log_audit_event(
            db=db,
            request=request,
            action="test_connection",
            entity_type="source",
            entity_id=source_id,
            user_id=actor_id,
            user_email=current_user.get("email"),
            changes={"success": result.get("success")},
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return result


@router.get("/{source_id}/schemas")
async def get_source_schemas(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Discover available schemas in source database (T043)."""
    service = SourceService(db)
    source = await service.get_source(source_id)
    if not source or not source.credential:
        raise HTTPException(status_code=404, detail="Источник не найден")

    try:
        password = await decrypt_password(db, source.credential.password_encrypted)
        if source.source_type == "jira":
            raise HTTPException(
                status_code=400,
                detail="Для Jira используйте endpoint /sources/{id}/jira/streams",
            )
        if source.source_type == "s3":
            return {"schemas": [source.database]}
        return {"schemas": await discover_schemas(
            source.host, source.port, source.database, source.username, password
        )}
    except Exception as exc:
        detail = "Не удалось получить список схем источника"
        if settings.debug:
            detail = f"{detail}: {exc}"
        raise HTTPException(
            status_code=400,
            detail=detail,
        )


@router.get("/{source_id}/schemas/{schema_name}/tables")
async def get_source_tables(
    source_id: UUID,
    schema_name: str,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Discover tables in a source schema (T044)."""
    service = SourceService(db)
    source = await service.get_source(source_id)
    if not source or not source.credential:
        raise HTTPException(status_code=404, detail="Источник не найден")

    try:
        password = await decrypt_password(db, source.credential.password_encrypted)
        if source.source_type == "jira":
            raise HTTPException(
                status_code=400,
                detail="Для Jira используйте endpoint /sources/{id}/jira/streams/{name}/schema",
            )
        if source.source_type == "s3":
            if schema_name != source.database:
                raise HTTPException(status_code=404, detail="Бакет не найден")
            return {"tables": await discover_s3_objects(
                source.host,
                source.port,
                source.database,
                source.username,
                password,
            )}
        return {"tables": await discover_tables(
            source.host, source.port, source.database, source.username, password, schema_name
        )}
    except HTTPException:
        raise
    except Exception as exc:
        detail = f"Не удалось получить таблицы схемы {schema_name}"
        if settings.debug:
            detail = f"{detail}: {exc}"
        raise HTTPException(
            status_code=400,
            detail=detail,
        )
