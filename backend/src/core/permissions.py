"""Role-based permission system."""

from enum import StrEnum


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
    "owner": {
        Permission.SOURCES_READ,
        Permission.SOURCES_WRITE,
        Permission.FLOWS_READ,
        Permission.FLOWS_WRITE,
        Permission.FLOWS_RUN,
        Permission.PREVIEW_READ,
        Permission.SCHEDULES_READ,
        Permission.SCHEDULES_WRITE,
        Permission.AUDIT_READ,
    },
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
    "viewer": {
        Permission.SOURCES_READ,
        Permission.FLOWS_READ,
        Permission.PREVIEW_READ,
        Permission.SCHEDULES_READ,
    },
}


def get_permissions_for_role(role: str) -> set[Permission]:
    return ROLE_PERMISSIONS.get(role, set())


KEYCLOAK_ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": set(Permission),
    "system:admin": set(Permission),
    "owner": ROLE_PERMISSIONS["owner"],
    "user": ROLE_PERMISSIONS["user"],
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
