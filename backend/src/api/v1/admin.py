"""System admin API for tenants, users, and memberships."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_system_db
from src.api.openapi_responses import (
    RESPONSE_400_BAD_REQUEST,
    RESPONSE_401_UNAUTHORIZED,
    RESPONSE_403_FORBIDDEN,
    RESPONSE_404_NOT_FOUND,
    RESPONSE_422_VALIDATION,
    merge_openapi_responses,
)
from src.middleware.auth import get_current_user
from src.models.tenant import Tenant
from src.models.user import User
from src.models.workspace_membership import WorkspaceMembership
from src.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["Admin"])


def require_system_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not bool(current_user.get("is_system_admin")) and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права системного администратора",
        )
    return current_user


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    subdomain: str = Field(..., min_length=3, max_length=63)
    schema_name: str | None = Field(default=None, max_length=63)
    keycloak_realm: str | None = Field(default=None, max_length=100)
    is_active: bool = True

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Acme Corp",
                "subdomain": "acme",
                "schema_name": "tenant_acme",
                "keycloak_realm": "gendwh",
                "is_active": True,
            }
        }
    }


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    subdomain: str | None = Field(default=None, min_length=3, max_length=63)
    keycloak_realm: str | None = Field(default=None, max_length=100)
    is_active: bool | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "Acme Corporation",
                "is_active": True,
            }
        }
    }


class MembershipResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    tenant_subdomain: str
    role: str
    revoked_at: datetime | None
    deleted_at: datetime | None


class TenantResponse(BaseModel):
    id: UUID
    name: str
    subdomain: str
    schema_name: str
    keycloak_realm: str | None
    is_active: bool
    deleted_at: datetime | None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                "name": "Acme Corp",
                "subdomain": "acme",
                "schema_name": "tenant_acme",
                "keycloak_realm": "gendwh",
                "is_active": True,
                "deleted_at": None,
            }
        },
    }


class UserCreate(BaseModel):
    keycloak_id: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    is_active: bool = True

    model_config = {
        "json_schema_extra": {
            "example": {
                "keycloak_id": "0a0b0c0d-1111-2222-3333-444455556666",
                "email": "owner@example.com",
                "is_active": True,
            }
        }
    }


class UserUpdate(BaseModel):
    keycloak_id: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "updated.owner@example.com",
                "is_active": True,
            }
        }
    }


class MembershipUpsert(BaseModel):
    tenant_id: UUID
    role: str = Field(..., pattern="^(owner|user|viewer)$")

    model_config = {
        "json_schema_extra": {
            "example": {
                "tenant_id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                "role": "owner",
            }
        }
    }


class UserResponse(BaseModel):
    id: UUID
    keycloak_id: str
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    memberships: list[MembershipResponse]


class TenantListResponse(BaseModel):
    items: list[TenantResponse]


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    available_roles: list[str]


def _serialize_tenant(tenant: Tenant) -> TenantResponse:
    return TenantResponse.model_validate(tenant)


def _serialize_user(user: User) -> UserResponse:
    memberships: list[MembershipResponse] = []
    for membership in sorted(
        list(getattr(user, "memberships", [])),
        key=lambda item: (str(getattr(item.workspace, "name", "")), str(item.created_at)),
    ):
        workspace = membership.workspace
        if workspace is None:
            continue
        memberships.append(
            MembershipResponse(
                id=membership.id,
                tenant_id=workspace.id,
                tenant_name=workspace.name,
                tenant_subdomain=workspace.subdomain,
                role=membership.role,
                revoked_at=membership.revoked_at,
                deleted_at=membership.deleted_at,
            )
        )
    return UserResponse(
        id=user.id,
        keycloak_id=user.keycloak_id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        memberships=memberships,
    )


@router.get(
    "/tenants",
    summary="Список tenants",
    description="Возвращает все tenants из system database.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
    ),
)
async def list_tenants(
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> TenantListResponse:
    service = AdminService(db)
    tenants = await service.list_tenants()
    return TenantListResponse(items=[_serialize_tenant(tenant) for tenant in tenants])


@router.post(
    "/tenants",
    status_code=status.HTTP_201_CREATED,
    summary="Создать tenant",
    description="Создает новый tenant, его schema metadata и системную запись для дальнейшей работы.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> TenantResponse:
    service = AdminService(db)
    try:
        tenant = await service.create_tenant(**body.model_dump())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_tenant(tenant)


@router.patch(
    "/tenants/{tenant_id}",
    summary="Обновить tenant",
    description="Изменяет display name, subdomain и административные параметры tenant.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def update_tenant(
    tenant_id: UUID,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> TenantResponse:
    service = AdminService(db)
    try:
        tenant = await service.update_tenant(tenant_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant не найден")
    return _serialize_tenant(tenant)


@router.delete(
    "/tenants/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить tenant",
    description="Удаляет tenant из system scope. Используйте с осторожностью.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def delete_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> None:
    service = AdminService(db)
    deleted = await service.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tenant не найден")


@router.get(
    "/users",
    summary="Список пользователей",
    description="Возвращает пользователей system scope и их memberships по workspace.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def list_users(
    search: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> UserListResponse:
    service = AdminService(db)
    users = await service.list_users(search=search, limit=limit, offset=offset)
    total = await service.count_users(search=search)
    return UserListResponse(
        items=[_serialize_user(user) for user in users],
        total=total,
        available_roles=service.available_roles(),
    )


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    summary="Создать пользователя",
    description="Создает локальную запись пользователя, связанную с Keycloak subject.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_422_VALIDATION,
    ),
)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> UserResponse:
    service = AdminService(db)
    try:
        user = await service.create_user(**body.model_dump())
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = await db.get(
        User,
        user.id,
        options=[selectinload(User.memberships).selectinload(WorkspaceMembership.workspace)],
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _serialize_user(user)


@router.patch(
    "/users/{user_id}",
    summary="Обновить пользователя",
    description="Меняет email, keycloak_id или флаг активности локального пользователя.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> UserResponse:
    service = AdminService(db)
    try:
        user = await service.update_user(user_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user = await db.get(
        User,
        user.id,
        options=[selectinload(User.memberships).selectinload(WorkspaceMembership.workspace)],
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _serialize_user(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить пользователя",
    description="Удаляет пользователя из system scope.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> None:
    service = AdminService(db)
    deleted = await service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Пользователь не найден")


@router.put(
    "/users/{user_id}/memberships",
    summary="Назначить membership",
    description="Создает или обновляет membership пользователя в выбранном tenant.",
    responses=merge_openapi_responses(
        RESPONSE_400_BAD_REQUEST,
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def upsert_membership(
    user_id: UUID,
    body: MembershipUpsert,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> UserResponse:
    service = AdminService(db)
    try:
        await service.set_membership(user_id=user_id, tenant_id=body.tenant_id, role=body.role)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = await db.get(
        User,
        user_id,
        options=[selectinload(User.memberships).selectinload(WorkspaceMembership.workspace)],
    )
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _serialize_user(user)


@router.delete(
    "/users/{user_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить membership",
    description="Удаляет membership пользователя из tenant.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def delete_membership(
    user_id: UUID,
    membership_id: UUID,
    db: AsyncSession = Depends(get_system_db),
    _: dict = Depends(require_system_admin),
) -> None:
    service = AdminService(db)
    deleted = await service.remove_membership(user_id=user_id, membership_id=membership_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Membership не найден")
