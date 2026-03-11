"""API dependencies - database, auth, workspace."""

from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.permissions import Permission
from src.core.tenant import current_tenant_id, current_tenant_schema, set_tenant_schema
from src.services.tenant_schema import ensure_tenant_schema_compatibility_once
from src.middleware.auth import get_current_user
from src.models.base import BusinessSessionLocal, SystemSessionLocal
from src.models.tenant import Tenant


async def get_system_db() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session for the system database."""
    async with SystemSessionLocal() as session:
        yield session


async def get_tenant_db(
    current_user: dict = Depends(get_current_user),
) -> AsyncGenerator[AsyncSession, None]:
    """Get a workspace-scoped session by the active workspace in auth context."""
    async with SystemSessionLocal() as session:
        workspace_id = current_user.get("active_workspace_id")
        if not workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Активный workspace не выбран",
            )
        tenant_result = await session.execute(
            select(Tenant.id, Tenant.schema_name).where(
                Tenant.id == workspace_id,
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
            )
        )
        tenant_row = tenant_result.one_or_none()
        if not tenant_row:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace не найден или не активен",
            )
        tenant_id, schema = tenant_row
        await ensure_tenant_schema_compatibility_once(schema)
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
    current_user: dict = Depends(get_current_user),
) -> UUID | None:
    """Return the authenticated public.users.id."""
    user_id = current_user.get("user_id")
    if not user_id:
        return None
    try:
        return UUID(str(user_id))
    except (TypeError, ValueError):
        return None
