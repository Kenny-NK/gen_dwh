"""API dependencies - database, auth, tenant (T018)."""

from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.permissions import Permission
from src.core.tenant import current_tenant_id, current_tenant_schema, set_tenant_schema
from src.middleware.auth import get_current_user
from src.models.base import BusinessSessionLocal, SystemSessionLocal
from src.models.tenant import Tenant
from src.models.user import User


async def get_system_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for the system database."""
    async with SystemSessionLocal() as session:
        yield session


async def get_tenant_db(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """Get a database session with tenant schema set."""
    async with SystemSessionLocal() as session:
        token_tenant_id: UUID | None = current_user.get("tenant_id")
        tenant_id: UUID | None = None
        schema: str | None = None
        header_tenant_id: UUID | None = None
        subdomain_tenant_id: UUID | None = None
        subdomain_schema: str | None = None

        header_tenant_raw = (request.headers.get("x-tenant-id") or "").strip()
        if header_tenant_raw:
            try:
                header_tenant_id = UUID(header_tenant_raw)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Некорректный X-Tenant-ID: ожидается UUID",
                ) from exc

            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name).where(
                    Tenant.id == header_tenant_id,
                    Tenant.is_active.is_(True),
                )
            )
            tenant_row = tenant_result.one_or_none()
            if not tenant_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Арендатор из X-Tenant-ID не найден или не активен",
                )
            tenant_id, schema = tenant_row

        if token_tenant_id and not header_tenant_id:
            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name).where(
                    Tenant.id == token_tenant_id,
                    Tenant.is_active.is_(True),
                )
            )
            tenant_row = tenant_result.one_or_none()
            if tenant_row:
                token_tenant_id, _ = tenant_row
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Арендатор из токена не найден или не активен",
                )

        host_header = request.headers.get("host") or ""
        if settings.trust_proxy_headers:
            host_header = request.headers.get("x-forwarded-host") or host_header
        host = host_header.split(",")[0].strip()
        hostname = host.split(":")[0].lower()
        host_parts = hostname.split(".")
        if len(host_parts) > 1 and host_parts[0] not in {"localhost", "www"}:
            subdomain = host_parts[0]
            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name).where(
                    Tenant.subdomain == subdomain,
                    Tenant.is_active.is_(True),
                )
            )
            tenant_row = tenant_result.one_or_none()
            if tenant_row:
                subdomain_tenant_id, subdomain_schema = tenant_row

        if header_tenant_id and subdomain_tenant_id and subdomain_tenant_id != header_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Арендатор в X-Tenant-ID не совпадает с tenant из subdomain",
            )

        if not tenant_id and subdomain_tenant_id and subdomain_schema:
            tenant_id, schema = subdomain_tenant_id, subdomain_schema

        if not tenant_id and token_tenant_id:
            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name).where(
                    Tenant.id == token_tenant_id,
                    Tenant.is_active.is_(True),
                )
            )
            tenant_row = tenant_result.one_or_none()
            if not tenant_row:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Арендатор из токена не найден или не активен",
                )
            tenant_id, schema = tenant_row

        if not tenant_id and settings.allow_realm_tenant_fallback:
            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name)
                .where(
                    Tenant.keycloak_realm == settings.keycloak_realm,
                    Tenant.is_active.is_(True),
                )
                .order_by(Tenant.created_at.asc())
                .limit(2)
            )
            tenant_rows = tenant_result.all()
            if len(tenant_rows) == 1:
                tenant_id, schema = tenant_rows[0]
            elif len(tenant_rows) > 1:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Невозможно определить арендатора автоматически: найдено несколько tenant в realm",
                )

        if token_tenant_id and tenant_id and tenant_id != token_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Арендатор в токене не совпадает с выбранным tenant",
            )

        if not schema or not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Арендатор не найден или не активен",
            )

        current_tenant_id.set(tenant_id)
        current_tenant_schema.set(schema)
        await set_tenant_schema(session, schema)
        yield session


async def get_business_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for the business database."""
    async with BusinessSessionLocal() as session:
        yield session


def require_permission(permission: Permission):
    async def checker(current_user: dict = Depends(get_current_user)) -> None:
        user_permissions = {str(value) for value in current_user.get("permissions", [])}
        if str(permission) not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Недостаточно прав: требуется '{permission}'",
            )

    return checker


async def get_current_actor_id(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> UUID | None:
    """Resolve local public.users.id for current Keycloak subject."""
    tenant_id = current_user.get("tenant_id") or current_tenant_id.get()
    if not tenant_id:
        return None
    user_result = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.keycloak_id == current_user["sub"],
            User.is_active.is_(True),
        )
    )
    user = user_result.scalar_one_or_none()
    if user:
        return user.id

    email = current_user.get("email") or f'{current_user["sub"]}@{settings.keycloak_realm}.local'
    role = current_user.get("role") or "user"

    existing_result = await db.execute(
        select(User).where(
            User.tenant_id == tenant_id,
            User.email == email,
            User.is_active.is_(True),
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        existing.keycloak_id = current_user["sub"]
        existing.role = role
        await db.commit()
        return existing.id

    user = User(
        tenant_id=tenant_id,
        keycloak_id=current_user["sub"],
        email=email,
        role=role,
        is_active=True,
    )
    db.add(user)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        retry_result = await db.execute(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.keycloak_id == current_user["sub"],
                User.is_active.is_(True),
            )
        )
        return retry_result.scalar_one_or_none()
    return user.id
