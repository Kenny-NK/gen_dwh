"""System admin service for tenants, users, and role memberships."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.tenant import validate_schema_name
from src.models.tenant import Tenant
from src.models.user import User
from src.models.workspace_membership import WorkspaceMembership
from src.services.tenant_schema import provision_tenant_schema

# Ensure tenant-scoped tables are registered in SQLAlchemy metadata before provisioning.
import src.models.audit  # noqa: F401
import src.models.cleanup_job  # noqa: F401
import src.models.flow  # noqa: F401
import src.models.flow_table  # noqa: F401
import src.models.notification  # noqa: F401
import src.models.notification_read  # noqa: F401
import src.models.preview_session  # noqa: F401
import src.models.run  # noqa: F401
import src.models.schedule  # noqa: F401
import src.models.source  # noqa: F401
import src.models.source_credential  # noqa: F401


_ROLE_CHOICES = {"owner", "user", "viewer"}
_SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


class AdminService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def available_roles() -> list[str]:
        return sorted(_ROLE_CHOICES)

    @staticmethod
    def _normalize_subdomain(value: str) -> str:
        normalized = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
        if not normalized or not _SUBDOMAIN_RE.fullmatch(normalized):
            raise ValueError(
                "Subdomain должен содержать только латиницу, цифры и дефис, длина 3-63 символа."
            )
        return normalized

    @classmethod
    def _normalize_schema_name(cls, schema_name: str | None, subdomain: str) -> str:
        if schema_name and str(schema_name).strip():
            return validate_schema_name(str(schema_name).strip().lower())
        return validate_schema_name(f"tenant_{subdomain.replace('-', '_')}")

    @staticmethod
    def _normalize_role(role: str) -> str:
        normalized = str(role or "").strip().lower()
        if normalized not in _ROLE_CHOICES:
            raise ValueError("Роль должна быть одной из: owner, user, viewer")
        return normalized

    async def list_tenants(self) -> list[Tenant]:
        result = await self.session.execute(
            select(Tenant)
            .where(Tenant.deleted_at.is_(None))
            .order_by(Tenant.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_tenant(
        self,
        *,
        name: str,
        subdomain: str,
        schema_name: str | None = None,
        keycloak_realm: str | None = None,
        is_active: bool = True,
        auto_commit: bool = True,
    ) -> Tenant:
        tenant = Tenant(
            name=str(name or "").strip(),
            subdomain=self._normalize_subdomain(subdomain),
            schema_name=self._normalize_schema_name(schema_name, subdomain),
            keycloak_realm=str(keycloak_realm or "").strip() or None,
            is_active=bool(is_active),
        )
        if not tenant.name:
            raise ValueError("Название tenant обязательно")
        self.session.add(tenant)
        await self.session.flush()
        await provision_tenant_schema(tenant.schema_name)
        if auto_commit:
            await self.session.commit()
        return tenant

    async def update_tenant(
        self,
        tenant_id: UUID,
        *,
        name: str | None = None,
        subdomain: str | None = None,
        keycloak_realm: str | None = None,
        is_active: bool | None = None,
        auto_commit: bool = True,
    ) -> Tenant | None:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            return None
        if name is not None:
            normalized_name = str(name).strip()
            if not normalized_name:
                raise ValueError("Название tenant обязательно")
            tenant.name = normalized_name
        if subdomain is not None:
            tenant.subdomain = self._normalize_subdomain(subdomain)
        if keycloak_realm is not None:
            tenant.keycloak_realm = str(keycloak_realm).strip() or None
        if is_active is not None:
            tenant.is_active = bool(is_active)
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return tenant

    async def delete_tenant(self, tenant_id: UUID, *, auto_commit: bool = True) -> bool:
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            return False
        now = datetime.now(UTC)
        tenant.deleted_at = now
        tenant.is_active = False
        membership_result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.tenant_id == tenant_id,
                WorkspaceMembership.deleted_at.is_(None),
            )
        )
        for membership in membership_result.scalars().all():
            membership.deleted_at = now
            membership.revoked_at = membership.revoked_at or now
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return True

    async def count_users(self, search: str | None = None) -> int:
        query = select(func.count(User.id))
        normalized_search = str(search or "").strip().lower()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            query = query.where(
                or_(
                    func.lower(User.email).like(pattern),
                    func.lower(User.keycloak_id).like(pattern),
                )
            )
        result = await self.session.execute(query)
        return int(result.scalar() or 0)

    async def list_users(
        self,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        query = (
            select(User)
            .options(
                selectinload(User.memberships).selectinload(WorkspaceMembership.workspace)
            )
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        normalized_search = str(search or "").strip().lower()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            query = query.where(
                or_(
                    func.lower(User.email).like(pattern),
                    func.lower(User.keycloak_id).like(pattern),
                )
            )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_user(
        self,
        *,
        keycloak_id: str,
        email: str,
        is_active: bool = True,
        auto_commit: bool = True,
    ) -> User:
        normalized_keycloak_id = str(keycloak_id or "").strip()
        normalized_email = str(email or "").strip().lower()
        if not normalized_keycloak_id:
            raise ValueError("Keycloak ID обязателен")
        if not normalized_email:
            raise ValueError("Email обязателен")
        user = User(
            keycloak_id=normalized_keycloak_id,
            email=normalized_email,
            is_active=bool(is_active),
        )
        self.session.add(user)
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return user

    async def update_user(
        self,
        user_id: UUID,
        *,
        keycloak_id: str | None = None,
        email: str | None = None,
        is_active: bool | None = None,
        auto_commit: bool = True,
    ) -> User | None:
        user = await self.session.get(User, user_id)
        if user is None:
            return None
        if keycloak_id is not None:
            normalized_keycloak_id = str(keycloak_id).strip()
            if not normalized_keycloak_id:
                raise ValueError("Keycloak ID обязателен")
            user.keycloak_id = normalized_keycloak_id
        if email is not None:
            normalized_email = str(email).strip().lower()
            if not normalized_email:
                raise ValueError("Email обязателен")
            user.email = normalized_email
        if is_active is not None:
            user.is_active = bool(is_active)
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return user

    async def delete_user(self, user_id: UUID, *, auto_commit: bool = True) -> bool:
        user = await self.session.get(User, user_id)
        if user is None:
            return False
        now = datetime.now(UTC)
        user.is_active = False
        membership_result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.deleted_at.is_(None),
            )
        )
        for membership in membership_result.scalars().all():
            membership.deleted_at = now
            membership.revoked_at = membership.revoked_at or now
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return True

    async def set_membership(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        role: str,
        auto_commit: bool = True,
    ) -> WorkspaceMembership:
        normalized_role = self._normalize_role(role)
        user = await self.session.get(User, user_id)
        if user is None:
            raise ValueError("Пользователь не найден")
        tenant = await self.session.get(Tenant, tenant_id)
        if tenant is None or tenant.deleted_at is not None:
            raise ValueError("Tenant не найден")
        result = await self.session.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.tenant_id == tenant_id,
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = WorkspaceMembership(
                user_id=user_id,
                tenant_id=tenant_id,
                role=normalized_role,
            )
            self.session.add(membership)
        else:
            membership.role = normalized_role
            membership.deleted_at = None
            membership.revoked_at = None
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return membership

    async def remove_membership(
        self,
        *,
        user_id: UUID,
        membership_id: UUID,
        auto_commit: bool = True,
    ) -> bool:
        membership = await self.session.get(WorkspaceMembership, membership_id)
        if membership is None or membership.user_id != user_id:
            return False
        now = datetime.now(UTC)
        membership.deleted_at = now
        membership.revoked_at = membership.revoked_at or now
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return True
