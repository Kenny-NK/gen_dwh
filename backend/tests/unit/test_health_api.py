import json

import pytest

from src.api import health


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _HealthySession:
    async def execute(self, query, params=None):
        return None


class _RedisStub:
    def __init__(self, pong: bool = True):
        self._pong = pong

    async def ping(self) -> bool:
        return self._pong


@pytest.mark.asyncio
async def test_health_check_returns_healthy(monkeypatch) -> None:
    monkeypatch.setattr(health, "SystemSessionLocal", lambda: _SessionContext(_HealthySession()))
    monkeypatch.setattr(health, "redis_client", _RedisStub(True))
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/local/bin/meltano")

    async def fake_cleanup_health() -> dict[str, object]:
        return {
            "status": "healthy",
            "failed_jobs": 0,
            "overdue_jobs": 0,
            "missing_tables": 0,
            "affected_tenants": [],
            "overdue_grace_seconds": 900,
        }

    monkeypatch.setattr(health, "_check_cleanup_job_backlog", fake_cleanup_health)

    response = await health.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "healthy"
    assert payload["background_tasks"]["cleanup_jobs"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_returns_degraded_for_cleanup_backlog(monkeypatch) -> None:
    monkeypatch.setattr(health, "SystemSessionLocal", lambda: _SessionContext(_HealthySession()))
    monkeypatch.setattr(health, "redis_client", _RedisStub(True))
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/local/bin/meltano")

    async def fake_cleanup_health() -> dict[str, object]:
        return {
            "status": "degraded",
            "failed_jobs": 1,
            "overdue_jobs": 2,
            "missing_tables": 0,
            "affected_tenants": ["tenant_a"],
            "overdue_grace_seconds": 900,
        }

    monkeypatch.setattr(health, "_check_cleanup_job_backlog", fake_cleanup_health)

    response = await health.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "degraded"
    assert payload["background_tasks"]["cleanup_jobs"]["failed_jobs"] == 1


@pytest.mark.asyncio
async def test_health_check_returns_503_for_core_dependency_failure(monkeypatch) -> None:
    class _FailingSession:
        async def execute(self, query, params=None):
            raise RuntimeError("db down")

    monkeypatch.setattr(health, "SystemSessionLocal", lambda: _SessionContext(_FailingSession()))
    monkeypatch.setattr(health, "redis_client", _RedisStub(True))
    monkeypatch.setattr(health.shutil, "which", lambda name: "/usr/local/bin/meltano")

    response = await health.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["background_tasks"]["cleanup_jobs"]["status"] == "skipped"
