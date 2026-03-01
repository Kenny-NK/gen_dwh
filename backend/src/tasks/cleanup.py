"""Cleanup tasks (T119)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text

from src.core.celery_app import celery_app
from src.models.base import SystemSessionLocal


@celery_app.task
def cleanup_expired_previews():
    """Remove expired preview schemas."""
    import asyncio

    asyncio.run(_cleanup_previews())


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
    import asyncio

    asyncio.run(_cleanup_audit())


async def _cleanup_audit():
    from src.models.audit import AuditEvent

    cutoff = datetime.now(UTC) - timedelta(days=100)
    async with SystemSessionLocal() as session:
        await session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < cutoff)
        )
        await session.commit()
