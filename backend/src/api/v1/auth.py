"""Workspace-aware auth endpoints."""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_system_db
from src.core.config import settings
from src.core.security import (
    AppSessionError,
    KeycloakUnavailableError,
    create_app_session_token,
    decode_app_session_token,
    decode_jwt,
)
from src.core.workspace_auth import (
    get_workspace_by_selector,
    sync_auth_context_from_keycloak_payload,
)
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


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: UUID | None = None
    slug: str | None = None


def _build_session_token(current_user: dict, *, active_workspace_id: UUID | None = None) -> str:
    selected_workspace = active_workspace_id or current_user.get("active_workspace_id")
    return create_app_session_token(
        subject=str(current_user["sub"]),
        user_id=str(current_user["user_id"]),
        email=str(current_user.get("email") or ""),
        active_workspace_id=str(selected_workspace) if selected_workspace else None,
        is_system_admin=bool(current_user.get("is_system_admin")),
    )


def _workspace_response(workspace: dict) -> dict:
    return {
        "id": workspace["id"],
        "slug": workspace["slug"],
        "name": workspace["name"],
        "role": workspace["role"],
    }


def _preserved_workspace_id(request: Request, current_user: dict) -> UUID | None:
    if current_user.get("active_workspace_id") is not None:
        return current_user.get("active_workspace_id")

    session_token = request.cookies.get(settings.auth_cookie_name)
    if not session_token:
        return None

    try:
        payload = decode_app_session_token(str(session_token))
    except AppSessionError:
        return None

    raw_workspace_id = payload.get("active_workspace_id")
    if not raw_workspace_id:
        return None

    try:
        workspace_id = UUID(str(raw_workspace_id))
    except (TypeError, ValueError):
        return None

    available_ids = {
        UUID(str(workspace.get("id") or workspace.get("workspace_id")))
        for workspace in current_user.get("workspaces", [])
        if workspace.get("id") or workspace.get("workspace_id")
    }
    if workspace_id not in available_ids:
        return None
    return workspace_id


@router.post("/session")
async def create_session(
    request: Request,
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
        payload = await decode_jwt(token)
        current_user = asdict(await sync_auth_context_from_keycloak_payload(payload))
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

    selected_workspace_id = _preserved_workspace_id(request, current_user)
    if selected_workspace_id is not None:
        current_user["active_workspace_id"] = selected_workspace_id

    session_token = _build_session_token(current_user, active_workspace_id=selected_workspace_id)
    _set_auth_cookie(response, session_token)
    return {
        "status": "ok",
        "active_workspace_id": (
            str(current_user["active_workspace_id"])
            if current_user.get("active_workspace_id")
            else None
        ),
        "workspace_count": len(current_user.get("workspaces", [])),
        "requires_workspace_selection": (
            current_user.get("active_workspace_id") is None
            and len(current_user.get("workspaces", [])) > 1
        ),
    }


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
    current_user: dict = Depends(get_current_user),
) -> dict:
    return {
        "id": current_user["user_id"],
        "email": current_user["email"],
        "role": current_user["role"],
        "roles": current_user.get("roles", []),
        "workspace_id": (
            str(current_user["active_workspace_id"])
            if current_user.get("active_workspace_id")
            else None
        ),
        "permissions": current_user.get("permissions", []),
        "is_system_admin": bool(current_user.get("is_system_admin")),
    }


@router.get("/workspaces")
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
) -> dict:
    items = [_workspace_response(workspace) for workspace in current_user.get("workspaces", [])]
    return {
        "items": items,
        "active_workspace_id": (
            str(current_user["active_workspace_id"])
            if current_user.get("active_workspace_id")
            else None
        ),
    }


@router.post("/switch-workspace")
async def switch_workspace(
    body: SwitchWorkspaceRequest,
    response: Response,
    db: AsyncSession = Depends(get_system_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    workspace = await get_workspace_by_selector(
        db,
        workspace_id=body.workspace_id,
        slug=body.slug,
    )
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace не найден")

    available_ids = {item["id"] for item in current_user.get("workspaces", [])}
    if str(workspace.id) not in available_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к выбранному workspace",
        )

    session_token = _build_session_token(current_user, active_workspace_id=workspace.id)
    _set_auth_cookie(response, session_token)
    return {
        "status": "ok",
        "active_workspace": {
            "id": str(workspace.id),
            "slug": workspace.subdomain,
            "name": workspace.name,
        },
    }


@router.get("/workspace")
async def get_workspace(
    db: AsyncSession = Depends(get_system_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    workspace_id = current_user.get("active_workspace_id")
    if not workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace не выбран")
    result = await db.execute(
        select(Tenant.id, Tenant.subdomain, Tenant.name, Tenant.is_active).where(
            Tenant.id == workspace_id
        )
    )
    workspace = result.one_or_none()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace не найден")

    workspace_row_id, subdomain, name, is_active = workspace
    return {
        "id": str(workspace_row_id),
        "slug": subdomain,
        "name": name,
        "is_active": is_active,
    }
