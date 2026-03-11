"""Workspace-aware authentication helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.core.permissions import get_permissions_for_role
from src.models.base import SystemSessionLocal
from src.models.tenant import Tenant
from src.models.user import User
from src.models.workspace_membership import WorkspaceMembership

_WORKSPACE_ROLE_RE = re.compile(
    r"^workspace:(?P<slug>[a-z0-9][a-z0-9_-]{0,62}):(?P<role>owner|user|viewer)$"
)
_ROLE_PRIORITY = {"viewer": 1, "user": 2, "owner": 3}


@dataclass(slots=True)
class WorkspaceAccess:
    workspace_id: UUID
    slug: str
    name: str
    role: str


@dataclass(slots=True)
class AuthContext:
    user_id: UUID
    sub: str
    email: str
    is_system_admin: bool
    roles: list[str]
    active_workspace_id: UUID | None
    role: str
    permissions: list[str]
    workspaces: list[WorkspaceAccess]


def _extract_all_roles(payload: dict) -> set[str]:
    realm_roles = payload.get("realm_access", {}).get("roles", [])
    client_roles = (
        payload.get("resource_access", {})
        .get(payload.get("azp", ""), {})
        .get("roles", [])
    )
    return {str(role).strip() for role in realm_roles if str(role).strip()} | {
        str(role).strip() for role in client_roles if str(role).strip()
    }


def _extract_requested_workspace_id(payload: dict) -> UUID | None:
    workspace_raw = payload.get("active_workspace_id")
    if not workspace_raw:
        return None
    try:
        return UUID(str(workspace_raw))
    except (TypeError, ValueError):
        return None


def extract_workspace_roles(roles: set[str]) -> dict[str, str]:
    workspace_roles: dict[str, str] = {}
    for raw_role in roles:
        match = _WORKSPACE_ROLE_RE.fullmatch(raw_role)
        if not match:
            continue
        slug = match.group("slug")
        role = match.group("role")
        current = workspace_roles.get(slug)
        if current is None or _ROLE_PRIORITY[role] > _ROLE_PRIORITY[current]:
            workspace_roles[slug] = role
    return workspace_roles


def _workspace_is_available(membership: WorkspaceMembership) -> bool:
    now = datetime.now(UTC)
    if membership.deleted_at is not None or membership.revoked_at is not None:
        return False
    if membership.demo_expires_at is not None and membership.demo_expires_at <= now:
        return False
    workspace = membership.workspace
    return bool(workspace and workspace.is_active and workspace.deleted_at is None)


async def _ensure_user(session: AsyncSession, *, subject: str, email: str) -> User:
    result = await session.execute(select(User).where(User.keycloak_id == subject))
    user = result.scalar_one_or_none()
    if user:
        if email and user.email != email:
            user.email = email
        user.is_active = True
        return user

    user = User(keycloak_id=subject, email=email or f"{subject}@local.invalid", is_active=True)
    session.add(user)
    await session.flush()
    return user


async def _build_auth_context(
    session: AsyncSession,
    *,
    user: User,
    roles: set[str],
    requested_workspace_id: UUID | None,
) -> AuthContext:
    is_system_admin = "system:admin" in roles or "admin" in roles

    workspace_result = await session.execute(
        select(WorkspaceMembership)
        .options(selectinload(WorkspaceMembership.workspace))
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(WorkspaceMembership.created_at.asc())
    )
    memberships = list(workspace_result.scalars().all())

    workspaces: list[WorkspaceAccess] = []
    if is_system_admin:
        tenant_result = await session.execute(
            select(Tenant)
            .where(Tenant.is_active.is_(True), Tenant.deleted_at.is_(None))
            .order_by(Tenant.created_at.asc())
        )
        for workspace in tenant_result.scalars().all():
            workspaces.append(
                WorkspaceAccess(
                    workspace_id=workspace.id,
                    slug=workspace.subdomain,
                    name=workspace.name,
                    role="admin",
                )
            )
    else:
        for membership in memberships:
            if not _workspace_is_available(membership):
                continue
            workspaces.append(
                WorkspaceAccess(
                    workspace_id=membership.workspace.id,
                    slug=membership.workspace.subdomain,
                    name=membership.workspace.name,
                    role=membership.role,
                )
            )

    workspace_map = {item.workspace_id: item for item in workspaces}
    active_workspace_id = None
    if requested_workspace_id in workspace_map:
        active_workspace_id = requested_workspace_id
    if active_workspace_id is None and len(workspaces) == 1:
        active_workspace_id = workspaces[0].workspace_id

    effective_role = "admin" if is_system_admin else "viewer"
    if active_workspace_id is not None and active_workspace_id in workspace_map:
        effective_role = workspace_map[active_workspace_id].role
    elif is_system_admin:
        effective_role = "admin"

    permissions = sorted(str(permission) for permission in get_permissions_for_role(effective_role))
    return AuthContext(
        user_id=user.id,
        sub=user.keycloak_id,
        email=user.email,
        is_system_admin=is_system_admin,
        roles=sorted(roles),
        active_workspace_id=active_workspace_id,
        role=effective_role,
        permissions=permissions,
        workspaces=workspaces,
    )


async def _load_workspace_access_from_roles(
    session: AsyncSession,
    workspace_roles: dict[str, str],
) -> list[WorkspaceAccess]:
    if not workspace_roles:
        return []
    tenant_result = await session.execute(
        select(Tenant)
        .where(
            Tenant.subdomain.in_(sorted(workspace_roles.keys())),
            Tenant.deleted_at.is_(None),
            Tenant.is_active.is_(True),
        )
        .order_by(Tenant.created_at.asc())
    )
    workspaces: list[WorkspaceAccess] = []
    for workspace in tenant_result.scalars().all():
        role = workspace_roles.get(workspace.subdomain)
        if not role:
            continue
        workspaces.append(
            WorkspaceAccess(
                workspace_id=workspace.id,
                slug=workspace.subdomain,
                name=workspace.name,
                role=role,
            )
        )
    return workspaces


def _build_auth_context_from_workspaces(
    *,
    user: User,
    roles: set[str],
    workspaces: list[WorkspaceAccess],
    requested_workspace_id: UUID | None,
    is_system_admin: bool,
) -> AuthContext:
    workspace_map = {item.workspace_id: item for item in workspaces}
    active_workspace_id = None
    if requested_workspace_id in workspace_map:
        active_workspace_id = requested_workspace_id
    if active_workspace_id is None and len(workspaces) == 1:
        active_workspace_id = workspaces[0].workspace_id

    effective_role = "admin" if is_system_admin else "viewer"
    if active_workspace_id is not None and active_workspace_id in workspace_map:
        effective_role = workspace_map[active_workspace_id].role
    elif is_system_admin:
        effective_role = "admin"

    permissions = sorted(str(permission) for permission in get_permissions_for_role(effective_role))
    return AuthContext(
        user_id=user.id,
        sub=user.keycloak_id,
        email=user.email,
        is_system_admin=is_system_admin,
        roles=sorted(roles),
        active_workspace_id=active_workspace_id,
        role=effective_role,
        permissions=permissions,
        workspaces=workspaces,
    )


async def sync_auth_context_from_keycloak_payload(payload: dict) -> AuthContext:
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="В токене отсутствует subject",
        )

    email = str(payload.get("email") or "").strip()
    roles = _extract_all_roles(payload)
    workspace_roles = extract_workspace_roles(roles)
    requested_workspace_id = _extract_requested_workspace_id(payload)

    async with SystemSessionLocal() as session:
        user = await _ensure_user(session, subject=subject, email=email)

        if workspace_roles:
            tenant_result = await session.execute(
                select(Tenant)
                .where(
                    Tenant.subdomain.in_(sorted(workspace_roles.keys())),
                    Tenant.deleted_at.is_(None),
                )
            )
            tenants = {tenant.subdomain: tenant for tenant in tenant_result.scalars().all()}
        else:
            tenants = {}

        membership_result = await session.execute(
            select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)
        )
        existing = {
            membership.tenant_id: membership
            for membership in membership_result.scalars().all()
        }
        matched_tenant_ids: set[UUID] = set()
        now = datetime.now(UTC)

        for slug, role in workspace_roles.items():
            workspace = tenants.get(slug)
            if workspace is None:
                continue
            matched_tenant_ids.add(workspace.id)
            membership = existing.get(workspace.id)
            if membership is None:
                membership = WorkspaceMembership(
                    user_id=user.id,
                    tenant_id=workspace.id,
                    role=role,
                )
                session.add(membership)
                existing[workspace.id] = membership
                continue
            membership.role = role
            membership.deleted_at = None
            membership.revoked_at = None

        for tenant_id, membership in existing.items():
            if tenant_id not in matched_tenant_ids:
                membership.deleted_at = membership.deleted_at or now

        await session.commit()
        return await _build_auth_context(
            session,
            user=user,
            roles=roles,
            requested_workspace_id=requested_workspace_id,
        )


async def load_auth_context_from_keycloak_payload(payload: dict) -> AuthContext:
    """Load auth context for a Keycloak token without mutating local memberships."""
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="В токене отсутствует subject",
        )

    email = str(payload.get("email") or "").strip()
    roles = _extract_all_roles(payload)
    requested_workspace_id = _extract_requested_workspace_id(payload)
    workspace_roles = extract_workspace_roles(roles)

    async with SystemSessionLocal() as session:
        result = await session.execute(select(User).where(User.keycloak_id == subject))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден или не синхронизирован",
            )

        is_system_admin = "system:admin" in roles or "admin" in roles
        if is_system_admin:
            context = await _build_auth_context(
                session,
                user=user,
                roles=roles,
                requested_workspace_id=requested_workspace_id,
            )
        else:
            token_workspaces = await _load_workspace_access_from_roles(session, workspace_roles)
            if token_workspaces or not settings.allow_realm_tenant_fallback:
                context = _build_auth_context_from_workspaces(
                    user=user,
                    roles=roles,
                    workspaces=token_workspaces,
                    requested_workspace_id=requested_workspace_id,
                    is_system_admin=False,
                )
            else:
                context = await _build_auth_context(
                    session,
                    user=user,
                    roles=roles,
                    requested_workspace_id=requested_workspace_id,
                )
        if email:
            context.email = email
        return context


async def load_auth_context_from_session(
    *,
    subject: str,
    user_id: UUID | None,
    active_workspace_id: UUID | None,
    is_system_admin: bool,
) -> AuthContext:
    async with SystemSessionLocal() as session:
        user: User | None = None
        if user_id is not None:
            user = await session.get(User, user_id)
        if user is None:
            result = await session.execute(select(User).where(User.keycloak_id == subject))
            user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден или деактивирован",
            )

        roles = {"system:admin"} if is_system_admin else set()
        context = await _build_auth_context(
            session,
            user=user,
            roles=roles,
            requested_workspace_id=active_workspace_id,
        )
        if not context.is_system_admin:
            membership_result = await session.execute(
                select(WorkspaceMembership.role, Tenant.subdomain)
                .join(Tenant, Tenant.id == WorkspaceMembership.tenant_id)
                .where(
                    WorkspaceMembership.user_id == user.id,
                    WorkspaceMembership.deleted_at.is_(None),
                    WorkspaceMembership.revoked_at.is_(None),
                    Tenant.deleted_at.is_(None),
                    Tenant.is_active.is_(True),
                )
            )
            context.roles = sorted(
                {f"workspace:{slug}:{role}" for role, slug in membership_result.all()}
            )
        return context


async def get_workspace_by_selector(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    slug: str | None = None,
) -> Tenant | None:
    if workspace_id is None and not (slug or "").strip():
        return None
    query = select(Tenant).where(Tenant.deleted_at.is_(None))
    if workspace_id is not None:
        query = query.where(Tenant.id == workspace_id)
    else:
        query = query.where(Tenant.subdomain == str(slug).strip())
    result = await session.execute(query)
    return result.scalar_one_or_none()
