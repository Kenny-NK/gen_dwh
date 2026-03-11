"""Authentication middleware with workspace-aware session handling."""

from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import settings
from src.core.security import (
    AppSessionError,
    KeycloakUnavailableError,
    decode_app_session_token,
    decode_jwt,
)
from src.core.tenant import current_tenant_id, current_tenant_schema
from src.core.workspace_auth import (
    load_auth_context_from_keycloak_payload,
    load_auth_context_from_session,
)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """Extract and validate auth context from bearer token or app session cookie."""
    bearer_token = credentials.credentials if credentials else None
    session_token = request.cookies.get(settings.auth_cookie_name)
    if not bearer_token and not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не авторизован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if bearer_token:
        try:
            payload = await decode_jwt(bearer_token)
            auth_context = await load_auth_context_from_keycloak_payload(payload)
        except KeycloakUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Сервис авторизации временно недоступен",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный или просроченный токен",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
    else:
        try:
            payload = decode_app_session_token(str(session_token))
            raw_workspace_id = payload.get("active_workspace_id")
            active_workspace_id = None
            if raw_workspace_id:
                try:
                    active_workspace_id = UUID(str(raw_workspace_id))
                except (TypeError, ValueError):
                    active_workspace_id = None
            raw_user_id = payload.get("uid")
            try:
                user_id = UUID(str(raw_user_id)) if raw_user_id else None
            except (TypeError, ValueError):
                user_id = None
            auth_context = await load_auth_context_from_session(
                subject=str(payload.get("sub") or ""),
                user_id=user_id,
                active_workspace_id=active_workspace_id,
                is_system_admin=bool(payload.get("is_system_admin")),
            )
        except AppSessionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительная сессия",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except HTTPException:
            raise

    user = {
        "user_id": str(auth_context.user_id),
        "sub": auth_context.sub,
        "email": auth_context.email,
        "tenant_id": auth_context.active_workspace_id,
        "active_workspace_id": auth_context.active_workspace_id,
        "role": auth_context.role,
        "roles": auth_context.roles,
        "permissions": auth_context.permissions,
        "is_system_admin": auth_context.is_system_admin,
        "workspaces": [
            {
                "id": str(workspace.workspace_id),
                "slug": workspace.slug,
                "name": workspace.name,
                "role": workspace.role,
            }
            for workspace in auth_context.workspaces
        ],
    }

    current_tenant_id.set(auth_context.active_workspace_id)
    current_tenant_schema.set(None)

    return user
