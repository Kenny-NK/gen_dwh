from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.api.deps import get_tenant_db
from src.main import app
from src.middleware.auth import get_current_user


@pytest.mark.asyncio
async def test_list_audit_returns_items_and_total(client, monkeypatch) -> None:
    async def fake_get_tenant_db():
        yield object()

    async def fake_get_current_user():
        return {
            "user_id": str(uuid4()),
            "sub": "kc-user-123",
            "email": "owner@example.com",
            "active_workspace_id": str(uuid4()),
            "role": "owner",
            "roles": ["workspace:acme:owner"],
            "permissions": ["audit:read"],
            "is_system_admin": False,
            "workspaces": [],
        }

    class _FakeAuditService:
        def __init__(self, _session):
            pass

        async def list_events(self, **_kwargs):
            return [
                type(
                    "AuditRow",
                    (),
                    {
                        "id": uuid4(),
                        "user_id": uuid4(),
                        "user_email": "user@example.com",
                        "action": "delete",
                        "entity_type": "flow",
                        "entity_id": uuid4(),
                        "changes": {"drop_target_tables": True},
                        "ip_address": "127.0.0.1",
                        "created_at": datetime.now(UTC),
                    },
                )()
            ]

        async def count_events(self, **_kwargs):
            return 12

    app.dependency_overrides[get_tenant_db] = fake_get_tenant_db
    app.dependency_overrides[get_current_user] = fake_get_current_user
    monkeypatch.setattr("src.api.v1.audit.AuditService", _FakeAuditService)

    try:
        response = await client.get("/api/v1/audit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 12
    assert len(payload["items"]) == 1
    assert payload["items"][0]["action"] == "delete"
