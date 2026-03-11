from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.api.deps import get_system_db
from src.main import app
from src.middleware.auth import get_current_user


@pytest.mark.asyncio
async def test_list_admin_users_returns_total_and_roles(client, monkeypatch) -> None:
    async def fake_get_system_db():
        yield object()

    async def fake_get_current_user():
        return {
            "user_id": str(uuid4()),
            "sub": "system-admin",
            "email": "admin@example.com",
            "active_workspace_id": None,
            "role": "admin",
            "roles": ["system:admin"],
            "permissions": ["audit:read", "flows:read"],
            "is_system_admin": True,
            "workspaces": [],
        }

    class _FakeAdminService:
        def __init__(self, _session):
            pass

        def available_roles(self):
            return ["owner", "user", "viewer"]

        async def list_users(self, **_kwargs):
            membership = type(
                "Membership",
                (),
                {
                    "id": uuid4(),
                    "role": "owner",
                    "revoked_at": None,
                    "deleted_at": None,
                    "created_at": datetime.now(UTC),
                    "workspace": type(
                        "Workspace",
                        (),
                        {
                            "id": uuid4(),
                            "name": "Acme",
                            "subdomain": "acme",
                        },
                    )(),
                },
            )()
            return [
                type(
                    "UserRow",
                    (),
                    {
                        "id": uuid4(),
                        "keycloak_id": "kc-123",
                        "email": "user@example.com",
                        "is_active": True,
                        "created_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                        "memberships": [membership],
                    },
                )()
            ]

        async def count_users(self, **_kwargs):
            return 4

    app.dependency_overrides[get_system_db] = fake_get_system_db
    app.dependency_overrides[get_current_user] = fake_get_current_user
    monkeypatch.setattr("src.api.v1.admin.AdminService", _FakeAdminService)

    try:
        response = await client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["available_roles"] == ["owner", "user", "viewer"]
    assert payload["items"][0]["memberships"][0]["tenant_subdomain"] == "acme"
