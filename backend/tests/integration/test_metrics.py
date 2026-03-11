import pytest
from httpx import ASGITransport, AsyncClient

from src.api import metrics
from src.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text(monkeypatch) -> None:
    async def fake_cleanup_job_metrics() -> dict[str, object]:
        return {
            "status": "degraded",
            "failed_jobs": 2,
            "overdue_jobs": 3,
            "missing_tables": 1,
            "affected_tenants": ["tenant_a", "tenant_b"],
        }

    monkeypatch.setattr(metrics, "_collect_cleanup_job_metrics", fake_cleanup_job_metrics)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    body = response.text
    assert "gendwh_cleanup_jobs_failed 2" in body
    assert "gendwh_cleanup_jobs_overdue 3" in body
    assert "gendwh_cleanup_jobs_missing_tables 1" in body
    assert 'gendwh_cleanup_jobs_status{status="degraded"} 1' in body
