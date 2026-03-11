"""Health check endpoint (T025)."""

from datetime import UTC, datetime, timedelta
import logging
import shutil

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from src.core.redis import redis_client
from src.core.tenant import validate_schema_name
from src.models.base import SystemSessionLocal
from src.models.tenant import Tenant

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)
_CLEANUP_JOB_OVERDUE_GRACE = timedelta(minutes=15)


async def _active_tenant_schemas() -> list[str]:
    async with SystemSessionLocal() as session:
        result = await session.execute(
            select(Tenant.schema_name).where(
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
            )
        )
        return [validate_schema_name(schema) for schema in result.scalars().all()]


async def _check_cleanup_job_backlog() -> dict[str, object]:
    overdue_cutoff = datetime.now(UTC) - _CLEANUP_JOB_OVERDUE_GRACE
    failed_jobs = 0
    overdue_jobs = 0
    missing_tables = 0
    affected_tenants: list[str] = []
    schemas = await _active_tenant_schemas()

    async with SystemSessionLocal() as session:
        for schema_name in schemas:
            regclass_result = await session.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": f"{schema_name}.cleanup_jobs"},
            )
            if regclass_result.scalar_one_or_none() is None:
                missing_tables += 1
                affected_tenants.append(schema_name)
                continue

            result = await session.execute(
                text(
                    f"""
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'failed') AS failed_jobs,
                        COUNT(*) FILTER (
                            WHERE status = 'pending'
                              AND available_at <= :overdue_cutoff
                        ) AS overdue_jobs
                    FROM "{schema_name}".cleanup_jobs
                    """
                ),
                {"overdue_cutoff": overdue_cutoff},
            )
            row = result.one()._mapping
            schema_failed = int(row["failed_jobs"] or 0)
            schema_overdue = int(row["overdue_jobs"] or 0)
            failed_jobs += schema_failed
            overdue_jobs += schema_overdue
            if schema_failed or schema_overdue:
                affected_tenants.append(schema_name)

    monitor_status = "healthy"
    if failed_jobs or overdue_jobs or missing_tables:
        monitor_status = "degraded"

    return {
        "status": monitor_status,
        "failed_jobs": failed_jobs,
        "overdue_jobs": overdue_jobs,
        "missing_tables": missing_tables,
        "affected_tenants": sorted(set(affected_tenants)),
        "overdue_grace_seconds": int(_CLEANUP_JOB_OVERDUE_GRACE.total_seconds()),
    }


@router.get("/health")
async def health_check() -> JSONResponse:
    """Check readiness of core dependencies and surface operational degradation."""
    checks: dict[str, object] = {"status": "healthy"}
    http_status = status.HTTP_200_OK

    try:
        async with SystemSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    try:
        pong = await redis_client.ping()
        checks["redis"] = "ok" if pong else "error"
        if not pong:
            checks["status"] = "unhealthy"
            http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    except Exception:
        checks["redis"] = "error"
        checks["status"] = "unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    checks["meltano"] = "ok" if shutil.which("meltano") else "missing"
    if checks["meltano"] == "missing":
        checks["status"] = "unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE

    if checks["status"] != "unhealthy":
        try:
            cleanup_health = await _check_cleanup_job_backlog()
        except Exception as exc:
            logger.exception("Failed to collect cleanup job health")
            checks["background_tasks"] = {
                "cleanup_jobs": {
                    "status": "unknown",
                    "error": (str(exc).strip() or exc.__class__.__name__)[:500],
                }
            }
            checks["status"] = "degraded"
        else:
            checks["background_tasks"] = {"cleanup_jobs": cleanup_health}
            if cleanup_health["status"] != "healthy":
                checks["status"] = "degraded"
    else:
        checks["background_tasks"] = {"cleanup_jobs": {"status": "skipped"}}

    return JSONResponse(status_code=http_status, content=checks)
