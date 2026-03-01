"""/auth/me endpoint (T022)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_tenant_db
from src.core.permissions import get_permissions_for_role
from src.core.tenant import get_current_tenant_id
from src.middleware.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
async def get_me(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get current user information."""
    _ = db
    permissions = [str(p) for p in get_permissions_for_role(current_user["role"])]
    tenant_id = current_user.get("tenant_id") or get_current_tenant_id()
    return {
        "id": current_user["sub"],
        "email": current_user["email"],
        "role": current_user["role"],
        "tenant_id": str(tenant_id) if tenant_id else None,
        "permissions": permissions,
    }
