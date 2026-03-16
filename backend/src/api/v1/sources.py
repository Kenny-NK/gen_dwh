"""Sources API endpoints (T041-T044)."""

import logging

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.audit_utils import log_audit_event
from src.api.deps import get_current_actor_id, get_system_db, get_tenant_db, require_permission
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
from src.models.source_credential import SourceCredential
from src.services.connection import decrypt_password, discover_s3_objects, discover_schemas, discover_tables
from src.services.source_service import SourceService

router = APIRouter(prefix="/sources", tags=["Sources"])
logger = logging.getLogger(__name__)


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Postgres ERP",
                "source_type": "postgres",
                "host": "erp-db.internal",
                "port": 5432,
                "database": "erp",
                "username": "readonly_user",
                "password": "change-me",
                "description": "Основная ERP база",
            }
        }
    }


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

    model_config = {
        "json_schema_extra": {
            "example": {
                "host": "erp-db-replica.internal",
                "port": 5432,
                "description": "Читаем из реплики",
            }
        }
    }


class SourceConnectionTestRequest(BaseModel):
    source_type: Literal["postgres", "s3", "jira"] = "postgres"
    jira_auth_type: Literal["basic_token", "basic_password", "pat_bearer"] | None = None
    host: str = Field(..., max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field("", max_length=255)
    username: str = Field(..., max_length=255)
    password: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "source_type": "jira",
                "jira_auth_type": "basic_token",
                "host": "https://company.atlassian.net",
                "port": 443,
                "database": "",
                "username": "integration@example.com",
                "password": "jira-api-token",
            }
        }
    }


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

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
                "name": "Postgres ERP",
                "source_type": "postgres",
                "description": "Основная ERP база",
                "host": "erp-db.internal",
                "port": 5432,
                "database": "erp",
                "username": "readonly_user",
                "connection_status": "valid",
                "last_validated_at": "2026-03-12T08:00:00Z",
                "validation_error": None,
                "extraction_config": None,
                "jira_auth_type": None,
                "jira_runtime_engine": None,
                "token_mask": None,
                "created_at": "2026-03-12T07:55:00Z",
                "updated_at": "2026-03-12T08:00:00Z",
            }
        },
    }


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "bdaf4b63-d361-4d17-b8b1-cf46fdbb0c39",
                        "name": "Postgres ERP",
                        "source_type": "postgres",
                        "description": "Основная ERP база",
                        "host": "erp-db.internal",
                        "port": 5432,
                        "database": "erp",
                        "username": "readonly_user",
                        "connection_status": "valid",
                        "last_validated_at": "2026-03-12T08:00:00Z",
                        "validation_error": None,
                        "extraction_config": None,
                        "jira_auth_type": None,
                        "jira_runtime_engine": None,
                        "token_mask": None,
                        "created_at": "2026-03-12T07:55:00Z",
                        "updated_at": "2026-03-12T08:00:00Z",
                    }
                ],
                "total": 1,
            }
        }
    }


class SourceConnectionTestResponse(BaseModel):
    success: bool
    message: str
    server_version: str | None = None
    latency_ms: float | None = None
    user_info: dict | None = None
    error_type: str | None = None
    suggestion: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "Connection successful",
                "server_version": "PostgreSQL 15.4",
                "latency_ms": 42.3,
                "user_info": None,
                "error_type": None,
                "suggestion": None,
            }
        }
    }


class SourceSchemasResponse(BaseModel):
    schemas: list[str]

    model_config = {"json_schema_extra": {"example": {"schemas": ["public", "sales", "erp"]}}}


class SourceTablesResponse(BaseModel):
    class TableColumn(BaseModel):
        name: str
        data_type: str
        is_nullable: bool | None = None
        is_primary_key: bool | None = None

    class TableInfo(BaseModel):
        name: str
        row_count: int = 0
        columns: list["SourceTablesResponse.TableColumn"] = Field(default_factory=list)
        format: str | None = None

    tables: list[TableInfo]

    model_config = {
        "json_schema_extra": {
            "example": {
                "tables": [
                    {
                        "name": "orders",
                        "row_count": 1048576,
                        "columns": [
                            {
                                "name": "id",
                                "data_type": "uuid",
                                "is_nullable": False,
                                "is_primary_key": True,
                            },
                            {
                                "name": "created_at",
                                "data_type": "timestamp with time zone",
                                "is_nullable": False,
                                "is_primary_key": False,
                            },
                        ],
                        "format": None,
                    }
                ]
            }
        }
    }


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
        payload["jira_runtime_engine"] = "native"
    payload["token_mask"] = await _mask_token(source, db)
    return SourceResponse.model_validate(payload)


# --- Endpoints ---

@router.get(
    "",
    summary="Список источников",
    description="Возвращает tenant-scoped список источников данных с пагинацией и фильтром по статусу подключения.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать источник",
    description=(
        "Создает источник данных, шифрует пароль/token и сразу выполняет проверку подключения. "
        "Если подключение невалидно, источник все равно создается со статусом `invalid`, чтобы "
        "его можно было исправить позже."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
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


@router.post(
    "/test-connection",
    summary="Проверить подключение без сохранения",
    description="Проверяет параметры подключения из payload без создания source в базе данных.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def test_source_connection_payload(
    body: SourceConnectionTestRequest,
    db: AsyncSession = Depends(get_system_db),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> SourceConnectionTestResponse:
    service = SourceService(db)
    try:
        result = await service.test_connection_payload(
            source_type=body.source_type,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
            jira_auth_type=body.jira_auth_type,
        )
        return SourceConnectionTestResponse.model_validate(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{source_id}",
    summary="Получить источник",
    description="Возвращает полную карточку одного источника по UUID.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
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


@router.patch(
    "/{source_id}",
    summary="Обновить источник",
    description=(
        "Обновляет параметры источника. Если поменялись connection fields или credentials, "
        "backend повторно валидирует подключение и ставит связанные потоки на паузу."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
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


@router.delete(
    "/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить источник",
    description=(
        "Мягко или жестко удаляет источник. Для soft delete используйте `hard_delete=false`. "
        "Если источник привязан к потокам, backend корректно обновляет их состояние."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
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


@router.post(
    "/{source_id}/test",
    summary="Проверить сохраненный источник",
    description="Повторно валидирует уже сохраненный источник и обновляет его `connection_status`.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def test_source_connection(
    source_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_tenant_db),
    actor_id: UUID | None = Depends(get_current_actor_id),
    _: None = Depends(require_permission(Permission.SOURCES_WRITE)),
    current_user: dict = Depends(get_current_user),
) -> SourceConnectionTestResponse:
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
    return SourceConnectionTestResponse.model_validate(result)


@router.get(
    "/{source_id}/schemas",
    summary="Получить список схем или bucket scope",
    description=(
        "Для PostgreSQL возвращает список схем. Для S3 возвращает bucket как единственную схему. "
        "Для Jira этот endpoint не используется."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def get_source_schemas(
    source_id: UUID,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> SourceSchemasResponse:
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
            return SourceSchemasResponse(schemas=[source.database])
        return SourceSchemasResponse(
            schemas=await discover_schemas(
                source.host, source.port, source.database, source.username, password
            )
        )
    except Exception as exc:
        detail = "Не удалось получить список схем источника"
        if settings.debug:
            detail = f"{detail}: {exc}"
        raise HTTPException(
            status_code=400,
            detail=detail,
        )


@router.get(
    "/{source_id}/schemas/{schema_name}/tables",
    summary="Получить таблицы или объекты источника",
    description=(
        "Для PostgreSQL возвращает таблицы указанной схемы. Для S3 возвращает объекты bucket. "
        "Для Jira используйте отдельные Jira endpoint'ы."
    ),
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def get_source_tables(
    source_id: UUID,
    schema_name: str,
    db: AsyncSession = Depends(get_tenant_db),
    _: None = Depends(require_permission(Permission.SOURCES_READ)),
    current_user: dict = Depends(get_current_user),
) -> SourceTablesResponse:
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
            return SourceTablesResponse(
                tables=await discover_s3_objects(
                    source.host,
                    source.port,
                    source.database,
                    source.username,
                    password,
                )
            )
        return SourceTablesResponse(
            tables=await discover_tables(
                source.host, source.port, source.database, source.username, password, schema_name
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to discover tables for source %s schema %s", source_id, schema_name)
        detail = f"Не удалось получить таблицы схемы {schema_name}"
        if settings.debug:
            detail = f"{detail}: {exc}"
        raise HTTPException(
            status_code=400,
            detail=detail,
        )
