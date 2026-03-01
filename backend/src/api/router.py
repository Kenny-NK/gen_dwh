"""API router with versioning (T024)."""

from fastapi import APIRouter

from src.api.v1 import auth, sources, flows, preview, runs, schedules, notifications, audit, dashboard

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(sources.router)
api_router.include_router(flows.router)
api_router.include_router(preview.router)
api_router.include_router(runs.router)
api_router.include_router(schedules.router)
api_router.include_router(notifications.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
