"""Role-based permission system (T021)."""

from enum import StrEnum
from functools import wraps
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
        Permission.SCHEDULES_WRITE,
    },
}


def get_permissions_for_role(role: str) -> set[Permission]:
    return ROLE_PERMISSIONS.get(role, set())


def require_permission(permission: Permission) -> Callable:
    """Dependency factory that checks if the current user has a specific permission."""

    def checker(current_user: dict) -> dict:
        user_role = current_user.get("role", "user")
        user_perms = get_permissions_for_role(user_role)
        if permission not in user_perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return current_user

    return checker
