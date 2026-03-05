"""Role-based permission system (T021)."""

from enum import StrEnum
from typing import Callable

from fastapi import HTTPException, status


class Permission(StrEnum):
    SOURCES_READ = "sources:read"
    SOURCES_WRITE = "sources:write"
    FLOWS_READ = "flows:read"
    FLOWS_WRITE = "flows:write"
    FLOWS_RUN = "flows:run"
    PREVIEW_READ = "preview:read"
    SCHEDULES_READ = "schedules:read"
    SCHEDULES_WRITE = "schedules:write"
    AUDIT_READ = "audit:read"
    PII_UNMASKED = "pii:unmasked"


ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": set(Permission),
    "user": {
        Permission.SOURCES_READ,
        Permission.SOURCES_WRITE,
        Permission.FLOWS_READ,
        Permission.FLOWS_WRITE,
        Permission.FLOWS_RUN,
        Permission.PREVIEW_READ,
        Permission.SCHEDULES_READ,
    },
}


def get_permissions_for_role(role: str) -> set[Permission]:
    return ROLE_PERMISSIONS.get(role, set())


KEYCLOAK_ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": set(Permission),
    "viewer": {
        Permission.SOURCES_READ,
        Permission.FLOWS_READ,
        Permission.PREVIEW_READ,
        Permission.SCHEDULES_READ,
    },
    "operator": {
        Permission.SOURCES_READ,
        Permission.FLOWS_READ,
        Permission.FLOWS_RUN,
        Permission.PREVIEW_READ,
        Permission.SCHEDULES_READ,
    },
    "auditor": {Permission.AUDIT_READ},
    "sources_read": {Permission.SOURCES_READ},
    "sources_write": {Permission.SOURCES_WRITE},
    "flows_read": {Permission.FLOWS_READ},
    "flows_write": {Permission.FLOWS_WRITE},
    "flows_run": {Permission.FLOWS_RUN},
    "preview_read": {Permission.PREVIEW_READ},
    "schedules_read": {Permission.SCHEDULES_READ},
    "schedules_write": {Permission.SCHEDULES_WRITE},
    "audit_read": {Permission.AUDIT_READ},
    "pii_unmasked": {Permission.PII_UNMASKED},
}


def permissions_from_keycloak_roles(roles: set[str]) -> set[Permission]:
    if "admin" in roles:
        return set(Permission)

    permissions: set[Permission] = set()
    for role in roles:
        permissions |= KEYCLOAK_ROLE_PERMISSIONS.get(role, set())
    return permissions


def require_permission(permission: Permission) -> Callable:
    """Dependency factory that checks if the current user has a specific permission."""

    def checker(current_user: dict) -> dict:
        declared_permissions = {
            str(item) for item in current_user.get("permissions", [])
        }
        if declared_permissions:
            user_perms = {
                permission
                for permission in Permission
                if str(permission) in declared_permissions
            }
        else:
            user_role = current_user.get("role", "user")
            user_perms = get_permissions_for_role(user_role)
        if permission not in user_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return current_user

    return checker
