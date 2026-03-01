"""Metrics collection endpoint (T127)."""

import time

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

router = APIRouter(tags=["metrics"])

# Simple metrics store
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


@router.get("/metrics")
async def get_metrics() -> dict:
    return _metrics
