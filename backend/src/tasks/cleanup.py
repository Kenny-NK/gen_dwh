"""Cleanup tasks (T119)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from src.core.celery_app import celery_app
from src.models.base import SystemSessionLocal


def _run_async_task(coro) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()


@celery_app.task
def cleanup_expired_previews():
    """Remove expired preview schemas."""
    _run_async_task(_cleanup_previews())


async def _cleanup_previews():
    from src.models.preview_session import PreviewSession

    async with SystemSessionLocal() as session:
        expired = await session.execute(
            delete(PreviewSession).where(
                PreviewSession.expires_at < datetime.now(UTC),
                PreviewSession.status.in_(["completed", "failed", "expired"]),
            )
        )
        await session.commit()


@celery_app.task
def cleanup_old_audit_events():
    """Remove audit events older than 100 days."""
    _run_async_task(_cleanup_audit())


async def _cleanup_audit():
    from src.models.audit import AuditEvent

    cutoff = datetime.now(UTC) - timedelta(days=100)
    async with SystemSessionLocal() as session:
        await session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < cutoff)
        )
        await session.commit()
