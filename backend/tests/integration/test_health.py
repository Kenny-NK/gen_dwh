import pytest
from httpx import ASGITransport, AsyncClient

from src.api import health
from src.main import app


@pytest.mark.asyncio
async def test_health_endpoint_returns_status(monkeypatch) -> None:
    class _Session:
        async def execute(self, query, params=None):
            return None

    class _SessionContext:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class _RedisStub:
        async def ping(self) -> bool:
            return True

    async def fake_cleanup_health() -> dict[str, object]:
        return {
            "status": "healthy",
            "failed_jobs": 0,
            "overdue_jobs": 0,
            "missing_tables": 0,
            "affected_tenants": [],
            "overdue_grace_seconds": 900,
        }

    monkeypatch.setattr(health, "SystemSessionLocal", lambda: _SessionContext())
    monkeypatch.setattr(health, "redis_client", _RedisStub())
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/local/bin/meltano")
    monkeypatch.setattr(health, "_check_cleanup_job_backlog", fake_cleanup_health)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert "background_tasks" in payload
