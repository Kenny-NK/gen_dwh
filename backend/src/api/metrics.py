"""Metrics collection endpoint (T127)."""

import time

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.health import _check_cleanup_job_backlog

router = APIRouter(tags=["Observability"])

_metrics: dict[str, int | float] = {
    "requests_total": 0,
    "errors_total": 0,
    "request_duration_sum": 0.0,
}


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        _metrics["requests_total"] += 1
        _metrics["request_duration_sum"] += duration
        if response.status_code >= 500:
            _metrics["errors_total"] += 1

        return response


async def _collect_cleanup_job_metrics() -> dict[str, object]:
    try:
        return await _check_cleanup_job_backlog()
    except Exception as exc:
        return {
            "status": "unknown",
            "failed_jobs": 0,
            "overdue_jobs": 0,
            "missing_tables": 0,
            "affected_tenants": [],
            "overdue_grace_seconds": 0,
            "error": (str(exc).strip() or exc.__class__.__name__)[:500],
        }


def _status_series(metric_name: str, *, current_status: str, statuses: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for status_name in statuses:
        value = 1 if current_status == status_name else 0
        lines.append(f'{metric_name}{{status="{status_name}"}} {value}')
    return lines


def _format_metrics_lines(cleanup_metrics: dict[str, object]) -> list[str]:
    cleanup_status = str(cleanup_metrics.get("status", "unknown"))
    failed_jobs = int(cleanup_metrics.get("failed_jobs") or 0)
    overdue_jobs = int(cleanup_metrics.get("overdue_jobs") or 0)
    missing_tables = int(cleanup_metrics.get("missing_tables") or 0)
    affected_tenants = len(cleanup_metrics.get("affected_tenants") or [])

    lines = [
        "# HELP gendwh_requests_total Total HTTP requests processed by API",
        "# TYPE gendwh_requests_total counter",
        f"gendwh_requests_total {_metrics['requests_total']}",
        "# HELP gendwh_errors_total Total HTTP 5xx responses",
        "# TYPE gendwh_errors_total counter",
        f"gendwh_errors_total {_metrics['errors_total']}",
        "# HELP gendwh_request_duration_seconds_sum Cumulative request duration in seconds",
        "# TYPE gendwh_request_duration_seconds_sum counter",
        f"gendwh_request_duration_seconds_sum {_metrics['request_duration_sum']}",
        "# HELP gendwh_cleanup_jobs_failed Number of terminally failed cleanup jobs across active tenants",
        "# TYPE gendwh_cleanup_jobs_failed gauge",
        f"gendwh_cleanup_jobs_failed {failed_jobs}",
        "# HELP gendwh_cleanup_jobs_overdue Number of pending cleanup jobs overdue for processing",
        "# TYPE gendwh_cleanup_jobs_overdue gauge",
        f"gendwh_cleanup_jobs_overdue {overdue_jobs}",
        "# HELP gendwh_cleanup_jobs_missing_tables Number of active tenant schemas missing cleanup_jobs table",
        "# TYPE gendwh_cleanup_jobs_missing_tables gauge",
        f"gendwh_cleanup_jobs_missing_tables {missing_tables}",
        "# HELP gendwh_cleanup_jobs_affected_tenants Number of active tenants affected by cleanup job degradation",
        "# TYPE gendwh_cleanup_jobs_affected_tenants gauge",
        f"gendwh_cleanup_jobs_affected_tenants {affected_tenants}",
        "# HELP gendwh_cleanup_jobs_status Cleanup jobs subsystem status where 1 marks the current state",
        "# TYPE gendwh_cleanup_jobs_status gauge",
        *_status_series(
            "gendwh_cleanup_jobs_status",
            current_status=cleanup_status,
            statuses=("healthy", "degraded", "unknown"),
        ),
    ]

    return lines


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description=(
        "Возвращает метрики в текстовом формате Prometheus exposition. "
        "Подходит для ручной проверки в браузере и для scrape из Prometheus."
    ),
    response_description="Текстовый поток метрик Prometheus",
)
async def get_metrics() -> Response:
    cleanup_metrics = await _collect_cleanup_job_metrics()
    lines = _format_metrics_lines(cleanup_metrics)
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
