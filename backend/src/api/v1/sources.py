"""Sources API endpoints (T041-T044)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_actor_id, get_tenant_db
from src.api.audit_utils import log_audit_event
from src.middleware.auth import get_current_user
from src.core.config import settings
from src.services.connection import decrypt_password, discover_s3_objects, discover_schemas, discover_tables
from src.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])


# --- Schemas ---

class SourceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    source_type: Literal["postgres", "s3"] = "postgres"
    host: str = Field(..., max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field(..., max_length=255)
    username: str = Field(..., max_length=255)
    password: str
    description: str | None = None


class SourceUpdate(BaseModel):
    name: str | None = None
    source_type: Literal["postgres", "s3"] | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    description: str | None = None


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Endpoints ---

@router.get("")
async def list_sources(
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[SourceResponse]:
    """List all sources (T041)."""
    service = SourceService(db)
    sources = await service.list_sources(status=status_filter, limit=limit, offset=offset)
    return [SourceResponse.model_validate(s) for s in sources]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> SourceResponse:
    """Create a new source connection (T041)."""
    service = SourceService(db)
    source = await service.create_source(
        name=body.name,
        source_type=body.source_type,
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password=body.password,
        description=body.description,
        created_by=actor_id,
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
    return SourceResponse.model_validate(source)


@router.get("/{source_id}")
async def get_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> SourceResponse:
    """Get source details (T041)."""
    service = SourceService(db)
    source = await service.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Источник не найден")
    return SourceResponse.model_validate(source)


@router.patch("/{source_id}")
async def update_source(
    source_id: UUID,
    body: SourceUpdate,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> SourceResponse:
    """Update source configuration (T041)."""
    service = SourceService(db)
    updates = body.model_dump(exclude_unset=True)
    source = await service.update_source(source_id, **updates)
    if not source:
        raise HTTPException(status_code=404, detail="Источник не найден")
    await log_audit_event(
        db=db,
        request=request,
        action="update",
        entity_type="source",
        entity_id=source.id,
        user_id=actor_id,
        user_email=current_user.get("email"),
        changes=updates,
    )
    return SourceResponse.model_validate(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> None:
    """Soft-delete a source (T041)."""
    service = SourceService(db)
    deleted = await service.delete_source(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Источник не найден")
    await log_audit_event(
        db=db,
        request=request,
        action="delete",
        entity_type="source",
        entity_id=source_id,
        user_id=actor_id,
        user_email=current_user.get("email"),
    )


@router.post("/{source_id}/test")
async def test_source_connection(
    source_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Test source connection (T042)."""
    service = SourceService(db)
    result = await service.test_source_connection(source_id)
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
    return result


@router.get("/{source_id}/schemas")
async def get_source_schemas(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> list[str]:
    """Discover available schemas in source database (T043)."""
    service = SourceService(db)
    source = await service.get_source(source_id)
    if not source or not source.credential:
        raise HTTPException(status_code=404, detail="Источник не найден")

    try:
        password = await decrypt_password(db, source.credential.password_encrypted)
        if source.source_type == "s3":
            return [source.database]
        return await discover_schemas(
            source.host, source.port, source.database, source.username, password
        )
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
    current_user: dict = Depends(get_current_user),
) -> list[dict]:
    """Discover tables in a source schema (T044)."""
    service = SourceService(db)
    source = await service.get_source(source_id)
    if not source or not source.credential:
        raise HTTPException(status_code=404, detail="Источник не найден")

    try:
        password = await decrypt_password(db, source.credential.password_encrypted)
        if source.source_type == "s3":
            if schema_name != source.database:
                raise HTTPException(status_code=404, detail="Бакет не найден")
            return await discover_s3_objects(
                source.host,
                source.port,
                source.database,
                source.username,
                password,
            )
        return await discover_tables(
            source.host, source.port, source.database, source.username, password, schema_name
        )
    except Exception as exc:
        detail = f"Не удалось получить таблицы схемы {schema_name}"
        if settings.debug:
            detail = f"{detail}: {exc}"
        raise HTTPException(
            status_code=400,
            detail=detail,
        )
