"""API dependencies - database, auth, tenant (T018)."""

from typing import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.tenant import current_tenant_id, current_tenant_schema, set_tenant_schema
from src.middleware.auth import get_current_user
from src.models.tenant import Tenant
from src.models.base import BusinessSessionLocal, SystemSessionLocal
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
        tenant_id: UUID | None = current_user.get("tenant_id")
        schema: str | None = None

        if tenant_id:
            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name).where(
                    Tenant.id == tenant_id,
                    Tenant.is_active.is_(True),
                )
            )
            tenant_row = tenant_result.one_or_none()
            if tenant_row:
                tenant_id, schema = tenant_row

        if not schema:
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
                    tenant_id, schema = tenant_row

        if not schema and settings.allow_realm_tenant_fallback:
            tenant_result = await session.execute(
                select(Tenant.id, Tenant.schema_name)
                .where(
                    Tenant.keycloak_realm == settings.keycloak_realm,
                    Tenant.is_active.is_(True),
                )
                .order_by(Tenant.created_at.asc())
            )
            tenant_row = tenant_result.first()
            if tenant_row:
                tenant_id, schema = tenant_row

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
