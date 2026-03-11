from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.api.deps import get_tenant_db
from src.main import app
from src.middleware.auth import get_current_user


@pytest.mark.asyncio
async def test_list_flows_uses_count_for_total(client, monkeypatch) -> None:
    async def fake_get_tenant_db():
        yield object()

    async def fake_get_current_user():
        return {
            "user_id": str(uuid4()),
            "sub": "kc-user-123",
            "email": "user@example.com",
            "active_workspace_id": str(uuid4()),
            "role": "owner",
            "roles": ["workspace:acme:owner"],
            "permissions": ["flows:read"],
            "is_system_admin": False,
            "workspaces": [],
        }

    class _FakeFlowService:
        def __init__(self, _session):
            pass

        async def list_flows(self, **_kwargs):
            return [
                type(
                    "FlowRow",
                    (),
                    {
                        "id": uuid4(),
                        "name": "Flow",
                        "description": None,
                        "source_id": uuid4(),
                        "target_schema": "public",
                        "target_table_prefix": None,
                        "status": "draft",
                        "status_reason": None,
                        "write_mode": "append",
                        "upsert_key": None,
                        "extraction_config": None,
                        "preview_mode": "auto",
                        "created_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    },
                )()
            ]

        async def count_flows(self, **_kwargs):
            return 7

    app.dependency_overrides[get_tenant_db] = fake_get_tenant_db
    app.dependency_overrides[get_current_user] = fake_get_current_user
    monkeypatch.setattr("src.api.v1.flows.FlowService", _FakeFlowService)

    try:
        response = await client.get("/api/v1/flows")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 7
    assert len(response.json()["items"]) == 1


@pytest.mark.asyncio
async def test_list_runs_uses_count_for_total(client, monkeypatch) -> None:
    async def fake_get_tenant_db():
        yield object()

    async def fake_get_current_user():
        return {
            "user_id": str(uuid4()),
            "sub": "kc-user-123",
            "email": "user@example.com",
            "active_workspace_id": str(uuid4()),
            "role": "owner",
            "roles": ["workspace:acme:owner"],
            "permissions": ["flows:read"],
            "is_system_admin": False,
            "workspaces": [],
        }

    class _FakeRunService:
        def __init__(self, _session):
            pass

        async def list_runs(self, **_kwargs):
            return [
                type(
                    "RunRow",
                    (),
                    {
                        "id": uuid4(),
                        "flow_id": uuid4(),
                        "run_number": 1,
                        "triggered_by": "manual",
                        "status": "success",
                        "started_at": None,
                        "completed_at": None,
                        "tables_processed": 1,
                        "records_processed": 10,
                        "source_records_total": 10,
                        "source_records_total_is_estimate": False,
                        "records_failed": 0,
                        "error_message": None,
                        "retry_count": 0,
                        "created_at": datetime.now(UTC),
                    },
                )()
            ]

        async def count_runs(self, **_kwargs):
            return 9

    app.dependency_overrides[get_tenant_db] = fake_get_tenant_db
    app.dependency_overrides[get_current_user] = fake_get_current_user
    monkeypatch.setattr("src.api.v1.runs.RunService", _FakeRunService)

    try:
        response = await client.get("/api/v1/runs")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 9
    assert len(response.json()["items"]) == 1
