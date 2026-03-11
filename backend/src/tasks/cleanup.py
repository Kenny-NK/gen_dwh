"""Cleanup tasks (T119)."""

from datetime import UTC, datetime, timedelta
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.celery_app import celery_app
from src.core.tenant import set_tenant_schema, validate_schema_name
from src.models.base import SystemSessionLocal
from src.models.cleanup_job import CleanupJob
from src.models.tenant import Tenant
from src.services.flow_service import FlowService
from src.services.notification_service import NotificationService
from src.services.tenant_schema import ensure_tenant_schema_compatibility_once

_CLEANUP_JOB_BATCH_SIZE = 25
_CLEANUP_JOB_ERROR_LIMIT = 2000
logger = logging.getLogger(__name__)


def _run_async_task(coro):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()


@celery_app.task
def cleanup_expired_previews():
    """Remove expired preview schemas."""
    _run_async_task(_cleanup_previews())


async def _active_tenant_schemas() -> list[str]:
    async with SystemSessionLocal() as session:
        result = await session.execute(
            select(Tenant.schema_name).where(
                Tenant.is_active.is_(True),
                Tenant.deleted_at.is_(None),
            )
        )
        return [str(row[0]) for row in result.all()]


async def _for_each_tenant_session(
    handler,
) -> int:
    processed = 0
    for tenant_schema in await _active_tenant_schemas():
        await ensure_tenant_schema_compatibility_once(tenant_schema)
        async with SystemSessionLocal() as session:
            await set_tenant_schema(session, tenant_schema)
            await handler(session)
            await session.commit()
            processed += 1
    return processed


async def _cleanup_previews():
    from src.models.preview_session import PreviewSession

    async def _delete_expired(session: AsyncSession) -> None:
        await session.execute(
            delete(PreviewSession).where(
                PreviewSession.expires_at < datetime.now(UTC),
                PreviewSession.status.in_(["completed", "failed", "expired"]),
            )
        )

    await _for_each_tenant_session(_delete_expired)


@celery_app.task
def cleanup_old_audit_events():
    """Remove audit events older than 100 days."""
    _run_async_task(_cleanup_audit())


async def _cleanup_audit():
    from src.models.audit import AuditEvent

    cutoff = datetime.now(UTC) - timedelta(days=100)

    async def _delete_old(session: AsyncSession) -> None:
        await session.execute(
            delete(AuditEvent).where(AuditEvent.created_at < cutoff)
        )

    await _for_each_tenant_session(_delete_old)


def _cleanup_retry_delay(attempt_count: int) -> timedelta:
    safe_attempt = max(1, int(attempt_count))
    minutes = min(5 * (2 ** (safe_attempt - 1)), 360)
    return timedelta(minutes=minutes)


async def _claim_cleanup_jobs(session: AsyncSession, *, limit: int) -> list[CleanupJob]:
    result = await session.execute(
        select(CleanupJob)
        .where(
            CleanupJob.status == "pending",
            CleanupJob.available_at <= datetime.now(UTC),
            CleanupJob.job_type == "drop_table",
        )
        .order_by(CleanupJob.available_at.asc(), CleanupJob.created_at.asc(), CleanupJob.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


def _format_cleanup_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:_CLEANUP_JOB_ERROR_LIMIT]


async def _commit_with_tenant(session: AsyncSession, tenant_schema: str) -> None:
    await session.commit()
    await set_tenant_schema(session, tenant_schema)


async def _notify_cleanup_failure(
    session: AsyncSession,
    *,
    job: CleanupJob,
    error_message: str,
) -> None:
    if job.requested_by is None:
        return
    await NotificationService(session).create_notification(
        type="warning",
        title="Требуется ручная очистка таблиц",
        message=(
            f"Не удалось автоматически очистить таблицу {job.target_schema}.{job.target_table}. "
            f"Проверьте business DB и завершите очистку вручную. Последняя ошибка: {error_message}"
        )[:2000],
        user_id=job.requested_by,
        related_entity_type=job.related_entity_type,
        related_entity_id=job.related_entity_id,
        auto_commit=False,
    )


async def _process_claimed_cleanup_jobs(
    session: AsyncSession,
    tenant_schema: str,
    jobs: list[CleanupJob],
) -> int:
    if not jobs:
        return 0

    flow_service = FlowService(session)
    processed = 0
    for job in jobs:
        now = datetime.now(UTC)
        job.attempt_count = int(job.attempt_count or 0) + 1
        job.last_attempt_at = now
        max_attempts = int(job.max_attempts or 8)

        try:
            await flow_service.execute_cleanup_plan([(job.target_schema, job.target_table)])
            job.status = "completed"
            job.completed_at = now
            job.last_error = None
            job.available_at = now
        except Exception as exc:
            error_message = _format_cleanup_error(exc)
            job.last_error = error_message
            if job.attempt_count >= max_attempts:
                job.status = "failed"
                job.completed_at = now
                try:
                    await _notify_cleanup_failure(session, job=job, error_message=error_message)
                except Exception:
                    logger.exception(
                        "Failed to create terminal cleanup notification for job %s",
                        job.id,
                    )
            else:
                job.status = "pending"
                job.available_at = now + _cleanup_retry_delay(job.attempt_count)
                job.completed_at = None
        await session.flush()
        await _commit_with_tenant(session, tenant_schema)
        processed += 1
    return processed


async def _process_cleanup_jobs_for_schema(
    tenant_schema: str,
    *,
    batch_size: int = _CLEANUP_JOB_BATCH_SIZE,
) -> int:
    normalized_schema = validate_schema_name(tenant_schema)
    await ensure_tenant_schema_compatibility_once(normalized_schema)

    processed = 0
    async with SystemSessionLocal() as session:
        await set_tenant_schema(session, normalized_schema)
        while True:
            jobs = await _claim_cleanup_jobs(session, limit=batch_size)
            if not jobs:
                break
            processed += await _process_claimed_cleanup_jobs(session, normalized_schema, jobs)
    return processed


async def _process_cleanup_jobs(tenant_schema: str | None = None) -> int:
    summary = await _process_cleanup_jobs_summary(tenant_schema)
    return int(summary["processed"])


async def _process_cleanup_jobs_summary(tenant_schema: str | None = None) -> dict[str, object]:
    schemas = [tenant_schema] if tenant_schema else await _active_tenant_schemas()
    processed = 0
    failed_schemas: list[dict[str, str]] = []

    for schema_name in schemas:
        try:
            processed += await _process_cleanup_jobs_for_schema(schema_name)
        except Exception as exc:
            logger.exception("Failed to process cleanup jobs for tenant schema %s", schema_name)
            failed_schemas.append(
                {
                    "tenant_schema": str(schema_name),
                    "error": _format_cleanup_error(exc),
                }
            )

    return {
        "processed": processed,
        "tenant_schema": tenant_schema,
        "failed_schemas": failed_schemas,
        "status": "degraded" if failed_schemas else "healthy",
    }


@celery_app.task(name="src.tasks.cleanup.process_cleanup_jobs")
def process_cleanup_jobs(tenant_schema: str | None = None) -> dict:
    """Process pending business DB cleanup jobs for one tenant or all active tenants."""
    return _run_async_task(_process_cleanup_jobs_summary(tenant_schema))
