"""Workspace-aware auth endpoints."""

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_system_db
from src.api.openapi_responses import (
    RESPONSE_401_UNAUTHORIZED,
    RESPONSE_403_FORBIDDEN,
    RESPONSE_404_NOT_FOUND,
    RESPONSE_422_VALIDATION,
    RESPONSE_503_UNAVAILABLE,
    merge_openapi_responses,
)
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

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Keycloak access token, который используется для создания backend session cookie.",
)


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
    workspace_id: UUID | None = Field(default=None, description="UUID workspace для переключения")
    slug: str | None = Field(default=None, description="Slug workspace; можно использовать вместо UUID")

    model_config = {
        "json_schema_extra": {
            "example": {
                "workspace_id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
            }
        }
    }


class SessionCreateResponse(BaseModel):
    status: str = Field(description="Статус операции")
    active_workspace_id: str | None = Field(
        default=None,
        description="UUID активного workspace после инициализации сессии",
    )
    workspace_count: int = Field(description="Количество доступных пользователю workspace")
    requires_workspace_selection: bool = Field(
        description="Нужно ли явно выбрать workspace перед дальнейшей работой",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "active_workspace_id": None,
                "workspace_count": 2,
                "requires_workspace_selection": True,
            }
        }
    }


class OperationStatusResponse(BaseModel):
    status: str = Field(description="Статус операции")

    model_config = {"json_schema_extra": {"example": {"status": "ok"}}}


class MeResponse(BaseModel):
    id: str = Field(description="Локальный UUID пользователя в public.users")
    email: str = Field(description="Email пользователя")
    role: str = Field(description="Эффективная роль в активном workspace")
    roles: list[str] = Field(description="Список ролей из auth context")
    workspace_id: str | None = Field(default=None, description="UUID активного workspace")
    permissions: list[str] = Field(description="Разрешения текущего пользователя")
    is_system_admin: bool = Field(description="Есть ли глобальные системные права администратора")

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "1d946a68-5998-40cc-bc61-539a8caeb7ea",
                "email": "owner@example.com",
                "role": "owner",
                "roles": ["workspace:acme:owner"],
                "workspace_id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                "permissions": [
                    "audit:read",
                    "flows:read",
                    "flows:run",
                    "flows:write",
                    "notifications:read",
                    "preview:read",
                    "schedules:read",
                    "schedules:write",
                    "sources:read",
                    "sources:write",
                ],
                "is_system_admin": False,
            }
        }
    }


class WorkspaceSummaryResponse(BaseModel):
    id: str
    slug: str
    name: str
    role: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                "slug": "acme",
                "name": "Acme Corp",
                "role": "owner",
            }
        }
    }


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceSummaryResponse]
    active_workspace_id: str | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {
                        "id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                        "slug": "acme",
                        "name": "Acme Corp",
                        "role": "owner",
                    },
                    {
                        "id": "150bdf87-508d-49ac-9ef5-d86f32f09fcb",
                        "slug": "beta",
                        "name": "Beta LLC",
                        "role": "viewer",
                    },
                ],
                "active_workspace_id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
            }
        }
    }


class SwitchWorkspaceResponse(BaseModel):
    status: str
    active_workspace: WorkspaceSummaryResponse

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "active_workspace": {
                    "id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                    "slug": "acme",
                    "name": "Acme Corp",
                    "role": "owner",
                },
            }
        }
    }


class ActiveWorkspaceResponse(BaseModel):
    id: str
    slug: str
    name: str
    is_active: bool

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "c767c7f5-2307-4ec9-83f5-7b194eb4d3e4",
                "slug": "acme",
                "name": "Acme Corp",
                "is_active": True,
            }
        }
    }


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


@router.post(
    "/session",
    summary="Создать backend-сессию",
    description=(
        "Принимает Keycloak bearer token, синхронизирует пользователя с локальной БД и "
        "устанавливает HTTP-only cookie backend-сессии. Этот endpoint удобно использовать "
        "первым в Swagger UI, чтобы затем тестировать остальные методы без ручной передачи "
        "Bearer токена в каждом запросе."
    ),
    response_description="Результат bootstrap backend-сессии",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_503_UNAVAILABLE,
    ),
)
async def create_session(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> SessionCreateResponse:
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
    return SessionCreateResponse(
        status="ok",
        active_workspace_id=(
            str(current_user["active_workspace_id"])
            if current_user.get("active_workspace_id")
            else None
        ),
        workspace_count=len(current_user.get("workspaces", [])),
        requires_workspace_selection=(
            current_user.get("active_workspace_id") is None
            and len(current_user.get("workspaces", [])) > 1
        ),
    )


@router.delete(
    "/session",
    summary="Очистить backend-сессию",
    description="Удаляет backend session cookie. Полезно для повторного bootstrap или ручного logout flow.",
)
async def clear_session(response: Response) -> OperationStatusResponse:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite.lower(),
    )
    return OperationStatusResponse(status="ok")


@router.get(
    "/me",
    summary="Получить текущий auth context",
    description=(
        "Возвращает локальный профиль пользователя, активный workspace, эффективную роль "
        "и список permissions. Используйте этот endpoint для проверки, что backend-сессия "
        "инициализирована корректно."
    ),
    responses=merge_openapi_responses(RESPONSE_401_UNAUTHORIZED),
)
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> MeResponse:
    return MeResponse(
        id=current_user["user_id"],
        email=current_user["email"],
        role=current_user["role"],
        roles=current_user.get("roles", []),
        workspace_id=(
            str(current_user["active_workspace_id"])
            if current_user.get("active_workspace_id")
            else None
        ),
        permissions=current_user.get("permissions", []),
        is_system_admin=bool(current_user.get("is_system_admin")),
    )


@router.get(
    "/workspaces",
    summary="Получить список доступных workspace",
    description=(
        "Возвращает все workspace, к которым у пользователя есть доступ. "
        "Используйте этот endpoint после `/auth/session`, если backend сообщил, "
        "что требуется выбор workspace."
    ),
    responses=merge_openapi_responses(RESPONSE_401_UNAUTHORIZED),
)
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
) -> WorkspaceListResponse:
    items = [_workspace_response(workspace) for workspace in current_user.get("workspaces", [])]
    return WorkspaceListResponse(
        items=items,
        active_workspace_id=(
            str(current_user["active_workspace_id"])
            if current_user.get("active_workspace_id")
            else None
        ),
    )


@router.post(
    "/switch-workspace",
    summary="Переключить активный workspace",
    description=(
        "Меняет активный workspace в backend session cookie. Можно передать либо "
        "`workspace_id`, либо `slug`. После переключения все tenant-scoped endpoint'ы "
        "будут работать в новом контексте."
    ),
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_403_FORBIDDEN,
        RESPONSE_404_NOT_FOUND,
        RESPONSE_422_VALIDATION,
    ),
)
async def switch_workspace(
    body: SwitchWorkspaceRequest,
    response: Response,
    db: AsyncSession = Depends(get_system_db),
    current_user: dict = Depends(get_current_user),
) -> SwitchWorkspaceResponse:
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
    return SwitchWorkspaceResponse(
        status="ok",
        active_workspace=WorkspaceSummaryResponse(
            id=str(workspace.id),
            slug=workspace.subdomain,
            name=workspace.name,
            role=next(
                (
                    str(item.get("role"))
                    for item in current_user.get("workspaces", [])
                    if str(item.get("id")) == str(workspace.id)
                ),
                current_user.get("role", "viewer"),
            ),
        ),
    )


@router.get(
    "/workspace",
    summary="Получить активный workspace",
    description="Возвращает карточку текущего активного workspace из backend auth context.",
    responses=merge_openapi_responses(
        RESPONSE_401_UNAUTHORIZED,
        RESPONSE_404_NOT_FOUND,
    ),
)
async def get_workspace(
    db: AsyncSession = Depends(get_system_db),
    current_user: dict = Depends(get_current_user),
) -> ActiveWorkspaceResponse:
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
    return ActiveWorkspaceResponse(
        id=str(workspace_row_id),
        slug=subdomain,
        name=name,
        is_active=is_active,
    )
