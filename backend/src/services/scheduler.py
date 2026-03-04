"""Celery tasks for flow execution (T076, T077, T078)."""

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from croniter import croniter

from celery.exceptions import Retry
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from src.core.celery_app import celery_app
from src.core.tenant import set_tenant_schema
from src.models.base import SystemSessionLocal
from src.models.flow import Flow
from src.models.flow_table import FlowTable
from src.models.run import Run
from src.models.schedule import Schedule
from src.models.tenant import Tenant
from src.services.connection import (
    build_s3_endpoint_url,
    decrypt_password,
    estimate_tables_row_count,
)
from src.services.meltano import run_meltano_elt
from src.services.run_service import RunService
from src.services.s3_loader import run_s3_to_postgres

# Ensure all ORM relationships are registered in worker-only imports.
import src.models.source  # noqa: F401
import src.models.source_credential  # noqa: F401
import src.models.user  # noqa: F401

_worker_loop: asyncio.AbstractEventLoop | None = None
logger = logging.getLogger(__name__)


def _advisory_lock_id(identifier: str) -> int:
    """Generate a stable advisory lock ID from a string."""
    return int(hashlib.md5(identifier.encode()).hexdigest()[:8], 16)


def _run_in_worker_loop(coro):
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coro)


async def _commit_with_tenant(session, tenant_schema: str) -> None:
    """Commit and restore tenant search_path for subsequent statements."""
    await session.commit()
    await set_tenant_schema(session, tenant_schema)


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
)
def execute_flow_run(self, run_id: str, flow_id: str, tenant_schema: str):
    """Execute a flow run via Meltano (T076)."""
    should_finalize = True
    try:
        _run_in_worker_loop(_execute_flow_run_async(self, run_id, flow_id, tenant_schema))
    except Retry:
        should_finalize = False
        raise
    finally:
        if should_finalize:
            _run_in_worker_loop(_ensure_run_terminal_status_async(run_id, flow_id, tenant_schema))


def _next_schedule_run(schedule: Schedule, base_time: datetime) -> datetime | None:
    if schedule.schedule_type == "cron" and schedule.cron_expression:
        return croniter(schedule.cron_expression, base_time).get_next(datetime)
    if schedule.schedule_type == "interval" and schedule.interval_minutes:
        return base_time + timedelta(minutes=int(schedule.interval_minutes))
    return None


@celery_app.task(name="src.services.scheduler.dispatch_due_schedules")
def dispatch_due_schedules() -> dict:
    """Dispatch runs for due schedules once per minute."""
    return _run_in_worker_loop(_dispatch_due_schedules_async())


async def _dispatch_due_schedules_async() -> dict:
    now = datetime.now(UTC)
    dispatched = 0

    async with SystemSessionLocal() as session:
        tenants_result = await session.execute(
            select(Tenant.schema_name).where(Tenant.is_active.is_(True))
        )
        tenant_schemas = [str(row[0]) for row in tenants_result.all()]

    for tenant_schema in tenant_schemas:
        async with SystemSessionLocal() as session:
            await set_tenant_schema(session, tenant_schema)
            due_result = await session.execute(
                select(Schedule, Flow)
                .join(Flow, Flow.id == Schedule.flow_id)
                .where(
                    Schedule.is_active.is_(True),
                    Schedule.schedule_type.in_(["cron", "interval"]),
                    Schedule.next_run_at.is_not(None),
                    Schedule.next_run_at <= now,
                    Flow.deleted_at.is_(None),
                    Flow.status != "draft",
                )
                .with_for_update(skip_locked=True)
            )
            due_items = due_result.all()
            run_service = RunService(session)

            for schedule, flow in due_items:
                has_table_result = await session.execute(
                    select(FlowTable.id).where(FlowTable.flow_id == flow.id).limit(1)
                )
                if has_table_result.scalar_one_or_none() is None:
                    schedule.next_run_at = _next_schedule_run(schedule, now)
                    await _commit_with_tenant(session, tenant_schema)
                    continue

                if await run_service.has_active_run(flow.id):
                    continue

                try:
                    run = await run_service.create_run(flow.id, triggered_by="scheduled")
                except ValueError:
                    continue

                schedule.last_run_at = now
                schedule.next_run_at = _next_schedule_run(schedule, now)
                await _commit_with_tenant(session, tenant_schema)

                try:
                    execute_flow_run.delay(str(run.id), str(flow.id), tenant_schema)
                    dispatched += 1
                except Exception as exc:
                    run.status = "failed"
                    run.error_message = f"Не удалось отправить запуск в очередь: {exc}"[:2000]
                    run.completed_at = datetime.now(UTC)
                    flow.status = "failed"
                    flow.status_reason = run.error_message
                    await _commit_with_tenant(session, tenant_schema)

    return {"dispatched": dispatched}


async def _mark_run_and_flow_failed(
    session,
    run_id: UUID,
    flow_id: UUID,
    tenant_schema: str,
    error_message: str,
) -> None:
    await session.rollback()
    await set_tenant_schema(session, tenant_schema)
    run = await session.get(Run, run_id)
    flow = await session.get(Flow, flow_id)
    if not run:
        logger.error(
            "Failed to mark run as failed: run %s not found in tenant schema %s",
            run_id,
            tenant_schema,
        )
    if not flow:
        logger.error(
            "Failed to update flow status: flow %s not found in tenant schema %s",
            flow_id,
            tenant_schema,
        )
    if run:
        run.status = "failed"
        run.error_message = error_message[:2000]
        run.completed_at = datetime.now(UTC)
    if flow:
        flow.status = "failed"
        flow.status_reason = error_message[:2000]
    await session.commit()


async def _ensure_run_terminal_status_async(run_id: str, flow_id: str, tenant_schema: str) -> None:
    """Prevent runs from being left in active states after worker task has exited."""
    run_uuid = UUID(str(run_id))
    flow_uuid = UUID(str(flow_id))
    fallback_error = "Запуск не завершен корректно: задача worker завершилась без финального статуса."

    async with SystemSessionLocal() as session:
        await set_tenant_schema(session, tenant_schema)
        run = await session.get(Run, run_uuid)
        flow = await session.get(Flow, flow_uuid)
        if not run:
            return

        if run.status in {"pending", "running"}:
            run.status = "failed"
            run.error_message = fallback_error
            run.completed_at = datetime.now(UTC)

            if flow and flow.status == "running":
                flow.status = "failed"
                flow.status_reason = fallback_error

            await session.commit()
            logger.warning(
                "Run %s was auto-finalized as failed after worker task exit (tenant=%s)",
                run_id,
                tenant_schema,
            )


async def _execute_flow_run_async(task, run_id: str, flow_id: str, tenant_schema: str):
    """Async implementation of flow execution."""
    run_uuid = UUID(str(run_id))
    flow_uuid = UUID(str(flow_id))
    lock_acquired = False
    lock_id = _advisory_lock_id(f"flow_{flow_id}")

    async with SystemSessionLocal() as session:
        await set_tenant_schema(session, tenant_schema)

        # Get run and flow
        run_result = await session.execute(select(Run).where(Run.id == run_uuid))
        run = run_result.scalar_one_or_none()
        if not run:
            return

        flow_result = await session.execute(
            select(Flow).options(selectinload(Flow.tables)).where(Flow.id == flow_uuid)
        )
        flow = flow_result.scalar_one_or_none()
        if not flow:
            return

        # Acquire advisory lock (T077)
        lock_result = await session.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        acquired = lock_result.scalar()
        if not acquired:
            run.status = "failed"
            run.error_message = "Другой запуск этого потока уже выполняется"
            run.completed_at = datetime.now(UTC)
            await session.commit()
            return

        lock_acquired = True

        try:
            # Update run status
            run.status = "running"
            run.records_processed = max(0, int(run.records_processed or 0))
            run.tables_processed = max(0, int(run.tables_processed or 0))
            if run.started_at is None:
                run.started_at = datetime.now(UTC)
            flow.status = "running"
            flow.status_reason = None
            await _commit_with_tenant(session, tenant_schema)

            # Get source credentials
            from src.models.source import Source

            source_result = await session.execute(
                select(Source).options(selectinload(Source.credential)).where(Source.id == flow.source_id)
            )
            source = source_result.scalar_one_or_none()
            if not source or not source.credential:
                run.status = "failed"
                run.error_message = "Источник не найден или отсутствуют учетные данные"
                run.completed_at = datetime.now(UTC)
                flow.status = "failed"
                flow.status_reason = run.error_message
                await session.commit()
                return

            try:
                password = await decrypt_password(session, source.credential.password_encrypted)
            except Exception as exc:
                raw_error = str(exc)
                if "Wrong key or corrupt data" in raw_error:
                    raw_error = (
                        "Не удалось расшифровать пароль источника. "
                        "Проверьте DB_ENCRYPTION_KEY или пересоздайте подключение источника."
                    )
                await _mark_run_and_flow_failed(session, run_uuid, flow_uuid, tenant_schema, raw_error)
                return

            source_type = (source.source_type or "postgres").lower()
            if source_type == "s3":
                source_config = {
                    "source_type": "s3",
                    "bucket": source.database,
                    "aws_access_key_id": source.username,
                    "aws_secret_access_key": password,
                    "aws_endpoint_url": build_s3_endpoint_url(source.host, source.port),
                }
            else:
                source_config = {
                    "source_type": "postgres",
                    "host": source.host,
                    "port": source.port,
                    "database": source.database,
                    "username": source.username,
                    "password": password,
                }

            target_config = {
                "schema": flow.target_schema,
                "write_mode": flow.write_mode,
                "upsert_key": flow.upsert_key,
            }

            tables = []
            for flow_table in getattr(flow, "tables", []):
                if source_type == "s3":
                    tables.append(
                        {
                            "source_key": flow_table.source_table,
                            "table_name": flow_table.target_table,
                        }
                    )
                    continue
                tables.append(
                    {
                        "schema": flow_table.source_schema,
                        "table": flow_table.source_table,
                        "replication_method": flow_table.replication_method,
                        "replication_key": flow_table.replication_key,
                    }
                )

            if source_type == "postgres":
                selected_pairs = [
                    (str(table["schema"]), str(table["table"]))
                    for table in tables
                    if table.get("schema") and table.get("table")
                ]
                if selected_pairs:
                    try:
                        estimated_total = await estimate_tables_row_count(
                            host=str(source_config["host"]),
                            port=int(source_config["port"]),
                            database=str(source_config["database"]),
                            username=str(source_config["username"]),
                            password=str(source_config["password"]),
                            tables=selected_pairs,
                        )
                        if estimated_total > 0:
                            run.source_records_total = estimated_total
                            run.source_records_total_is_estimate = True
                            await _commit_with_tenant(session, tenant_schema)
                    except Exception as exc:
                        logger.warning(
                            "Failed to estimate source rows for flow_id=%s run_id=%s: %s",
                            flow_id,
                            run_id,
                            exc,
                        )

            last_progress_commit_at = 0.0

            async def _on_progress(
                records_processed: int,
                source_total: int | None,
            ) -> None:
                nonlocal last_progress_commit_at
                changed = False

                processed_value = max(0, int(records_processed or 0))
                if processed_value > int(run.records_processed or 0):
                    run.records_processed = processed_value
                    changed = True

                if source_total is not None and source_total > 0:
                    total_value = int(source_total)
                    if int(run.source_records_total or 0) != total_value:
                        run.source_records_total = total_value
                        run.source_records_total_is_estimate = False
                        changed = True

                if not changed:
                    return

                now_monotonic = time.monotonic()
                if now_monotonic - last_progress_commit_at < 1.5:
                    return
                last_progress_commit_at = now_monotonic
                await _commit_with_tenant(session, tenant_schema)

            state_id = f"{tenant_schema}_{flow_id}"

            if source_type == "s3":
                result = await run_s3_to_postgres(
                    source_config=source_config,
                    target_config=target_config,
                    tables=tables,
                    progress_callback=_on_progress,
                )
            else:
                # Execute Meltano run for PostgreSQL source flows
                result = await run_meltano_elt(
                    source_config,
                    target_config,
                    state_id,
                    tables=tables,
                    source_type=source_type,
                    progress_callback=_on_progress,
                )

            if result.success:
                run.status = "success"
                run.records_processed = max(int(run.records_processed or 0), int(result.records_processed or 0))
                run.tables_processed = result.tables_processed
                result_source_total = getattr(result, "source_records_total", None)
                if result_source_total is not None and result_source_total > 0:
                    run.source_records_total = int(result_source_total)
                    run.source_records_total_is_estimate = False
                run.meltano_state_file = result.state_file
                flow.status = "success"
                flow.status_reason = None
            else:
                # Retry logic (T078)
                non_retryable_markers = (
                    "Meltano project directory not found",
                    "Meltano CLI not found",
                    "No such option: --state-id",
                    "No such file or directory",
                    "Unsupported S3 file extension",
                    "не содержит колонок",
                    "Upsert key",
                )
                can_retry = task.request.retries < 5 and not any(
                    marker in (result.error_message or "")
                    for marker in non_retryable_markers
                )
                if can_retry:
                    run.retry_count = task.request.retries + 1
                    await session.commit()
                    raise task.retry(exc=Exception(result.error_message))

                run.status = "failed"
                run.error_message = result.error_message
                flow.status = "failed"
                flow.status_reason = result.error_message

            run.completed_at = datetime.now(UTC)
            await session.commit()
        except Retry:
            raise
        except Exception as exc:
            logger.exception(
                "Unhandled flow run error for run_id=%s flow_id=%s tenant=%s",
                run_id,
                flow_id,
                tenant_schema,
            )
            await _mark_run_and_flow_failed(session, run_uuid, flow_uuid, tenant_schema, str(exc))

        finally:
            # Release advisory lock
            if lock_acquired:
                try:
                    await session.rollback()
                    await session.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": lock_id},
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
