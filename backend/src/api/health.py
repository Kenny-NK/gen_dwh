"""Health check endpoint (T025)."""

import shutil

from fastapi import APIRouter
from sqlalchemy import text

from src.core.redis import redis_client
from src.models.base import SystemSessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Check health of all services."""
    checks = {"status": "healthy"}

    # Check system database
    try:
        async with SystemSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "unhealthy"

    # Check Redis
    try:
        pong = await redis_client.ping()
        checks["redis"] = "ok" if pong else "error"
        if not pong:
            checks["status"] = "unhealthy"
    except Exception:
        checks["redis"] = "error"
        checks["status"] = "unhealthy"

    # Check Meltano CLI availability
    checks["meltano"] = "ok" if shutil.which("meltano") else "missing"

    return checks
