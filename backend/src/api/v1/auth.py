"""/auth/me endpoint (T022)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_actor_id, get_tenant_db
from src.core.config import settings
from src.core.tenant import get_current_tenant_id
from src.core.security import KeycloakUnavailableError, decode_jwt
from src.middleware.auth import get_current_user
from src.models.tenant import Tenant

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite.lower(),
        max_age=settings.auth_cookie_max_age_seconds,
        path="/",
    )


@router.post("/session")
async def create_session(
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        await decode_jwt(token)
    except KeycloakUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сервис авторизации временно недоступен",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или просроченный токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _set_auth_cookie(response, token)
    return {"status": "ok"}


@router.delete("/session")
async def clear_session(response: Response) -> dict:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite.lower(),
    )
    return {"status": "ok"}


@router.get("/me")
async def get_me(
    db: AsyncSession = Depends(get_tenant_db),
    actor_id = Depends(get_current_actor_id),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Get current user information."""
    _ = db
    tenant_id = current_user.get("tenant_id") or get_current_tenant_id()
    return {
        "id": str(actor_id) if actor_id else current_user["sub"],
        "email": current_user["email"],
        "role": current_user["role"],
        "roles": current_user.get("roles", []),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "permissions": current_user.get("permissions", []),
    }


@router.get("/tenant")
async def get_tenant(
    db: AsyncSession = Depends(get_tenant_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    tenant_id = current_user.get("tenant_id") or get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Арендатор не найден")
    result = await db.execute(
        select(Tenant.id, Tenant.subdomain, Tenant.name, Tenant.is_active).where(Tenant.id == tenant_id)
    )
    tenant = result.one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Арендатор не найден")

    tenant_row_id, subdomain, name, is_active = tenant
    return {
        "id": str(tenant_row_id),
        "subdomain": subdomain,
        "name": name,
        "is_active": is_active,
        "features": {
            "max_sources": None,
            "max_flows": None,
            "max_concurrent_runs": None,
        },
    }
