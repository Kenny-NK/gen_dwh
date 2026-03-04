"""Authentication middleware with JWT validation (T020)."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import settings
from src.core.permissions import get_permissions_for_role, permissions_from_keycloak_roles
from src.core.security import KeycloakUnavailableError, decode_jwt
from src.core.tenant import current_tenant_id, current_tenant_schema

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Extract and validate JWT token, return user info."""
    token = credentials.credentials if credentials else request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = await decode_jwt(token)
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

    tenant_id_raw = payload.get("tenant_id")
    tenant_id = None
    if tenant_id_raw:
        try:
            tenant_id = UUID(str(tenant_id_raw))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Некорректный tenant_id в токене",
            )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="В токене отсутствует subject",
        )

    roles = payload.get("realm_access", {}).get("roles", [])
    client_roles = (
        payload.get("resource_access", {})
        .get(payload.get("azp", ""), {})
        .get("roles", [])
    )
    all_roles = {str(role) for role in roles} | {str(role) for role in client_roles}
    role = "admin" if "admin" in all_roles else "user"
    resolved_permissions = permissions_from_keycloak_roles(all_roles)
    if not resolved_permissions:
        resolved_permissions = get_permissions_for_role(role)
    permissions = [str(permission) for permission in resolved_permissions]

    user = {
        "sub": str(sub),
        "email": payload.get("email", ""),
        "tenant_id": tenant_id,
        "role": role,
        "roles": sorted(all_roles),
        "permissions": permissions,
    }

    # Set tenant context, schema is resolved from DB in dependency.
    current_tenant_id.set(tenant_id)
    current_tenant_schema.set(None)

    return user
