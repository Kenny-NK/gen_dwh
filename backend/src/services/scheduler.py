"""Celery tasks for flow execution (T076, T077, T078)."""

import hashlib
from datetime import UTC, datetime

from celery.exceptions import Retry
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from src.core.celery_app import celery_app
from src.core.tenant import set_tenant_schema
from src.models.base import SystemSessionLocal
from src.models.flow import Flow
from src.models.run import Run
from src.services.connection import decrypt_password
from src.services.meltano import run_meltano_elt


def _advisory_lock_id(identifier: str) -> int:
    """Generate a stable advisory lock ID from a string."""
    return int(hashlib.md5(identifier.encode()).hexdigest()[:8], 16)


@celery_app.task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
)
def execute_flow_run(self, run_id: str, flow_id: str, tenant_schema: str):
    """Execute a flow run via Meltano (T076)."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_execute_flow_run_async(self, run_id, flow_id, tenant_schema))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        asyncio.set_event_loop(None)
        loop.close()


async def _execute_flow_run_async(task, run_id: str, flow_id: str, tenant_schema: str):
    """Async implementation of flow execution."""
    async with SystemSessionLocal() as session:
        await set_tenant_schema(session, tenant_schema)

        # Get run and flow
        run_result = await session.execute(select(Run).where(Run.id == run_id))
        run = run_result.scalar_one_or_none()
        if not run:
            return

        flow_result = await session.execute(select(Flow).options(selectinload(Flow.tables)).where(Flow.id == flow_id))
        flow = flow_result.scalar_one_or_none()
        if not flow:
            return

        # Acquire advisory lock (T077)
        lock_id = _advisory_lock_id(f"flow_{flow_id}")
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

        try:
            # Update run status
            run.status = "running"
            run.started_at = datetime.now(UTC)
            flow.status = "running"
            await session.commit()

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

            password = await decrypt_password(session, source.credential.password_encrypted)

            source_config = {
                "host": source.host,
                "port": source.port,
                "database": source.database,
                "username": source.username,
                "password": password,
            }

            target_config = {
                "schema": flow.target_schema,
            }

            tables = []
            for flow_table in getattr(flow, "tables", []):
                tables.append(
                    {
                        "schema": flow_table.source_schema,
                        "table": flow_table.source_table,
                        "replication_method": flow_table.replication_method,
                        "replication_key": flow_table.replication_key,
                    }
                )

            state_id = f"{tenant_schema}_{flow_id}"

            # Execute Meltano run
            result = await run_meltano_elt(source_config, target_config, state_id, tables=tables)

            if result.success:
                run.status = "success"
                run.records_processed = result.records_processed
                run.tables_processed = result.tables_processed
                run.meltano_state_file = result.state_file
                flow.status = "success"
            else:
                # Retry logic (T078)
                if task.request.retries < 5:
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
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(UTC)
            flow.status = "failed"
            flow.status_reason = run.error_message
            await session.commit()

        finally:
            # Release advisory lock
            await session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id},
            )
