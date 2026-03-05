"""Run service (T079)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.celery_app import celery_app
from src.models.flow import Flow
from src.models.run import Run


class RunService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _revoke_task(task_id: str | None) -> None:
        if not task_id:
            return
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        except Exception:
            # Cancellation is best-effort at broker/worker level; DB state remains source of truth.
            return

    async def list_runs(
        self,
        flow_id: UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Run]:
        query = select(Run)
        if flow_id:
            query = query.where(Run.flow_id == flow_id)
        if status:
            query = query.where(Run.status == status)
        query = query.order_by(Run.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_run(self, run_id: UUID) -> Run | None:
        result = await self.session.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()

    async def get_run_for_flow(self, run_id: UUID, flow_id: UUID) -> Run | None:
        result = await self.session.execute(
            select(Run).where(Run.id == run_id, Run.flow_id == flow_id)
        )
        return result.scalar_one_or_none()

    async def create_run(
        self,
        flow_id: UUID,
        triggered_by: str = "manual",
        auto_commit: bool = True,
    ) -> Run:
        for _ in range(3):
            flow_lock = await self.session.execute(
                select(Flow.id).where(Flow.id == flow_id, Flow.deleted_at.is_(None)).with_for_update()
            )
            if flow_lock.scalar_one_or_none() is None:
                raise ValueError("Flow not found")

            max_num = await self.session.execute(
                select(func.coalesce(func.max(Run.run_number), 0)).where(Run.flow_id == flow_id)
            )
            next_number = max_num.scalar() + 1

            run = Run(
                flow_id=flow_id,
                run_number=next_number,
                triggered_by=triggered_by,
                status="pending",
            )
            self.session.add(run)
            try:
                await self.session.flush()
                if auto_commit:
                    await self.session.commit()
                return run
            except IntegrityError:
                await self.session.rollback()

        raise ValueError("Could not allocate unique run number")

    async def cancel_run(
        self,
        run_id: UUID,
        flow_id: UUID | None = None,
        auto_commit: bool = True,
    ) -> Run | None:
        run = await self.get_run_for_flow(run_id, flow_id) if flow_id else await self.get_run(run_id)
        if not run or run.status not in ("pending", "running"):
            return None
        self._revoke_task(run.celery_task_id)
        run.status = "cancelled"
        run.error_message = "Запуск отменен пользователем."
        run.completed_at = datetime.now(UTC)
        run.celery_task_id = None
        flow = await self.session.get(Flow, run.flow_id)
        if flow and flow.status == "running":
            flow.status = "paused"
            flow.status_reason = "Запуск остановлен пользователем."
            flow.pause_requested = False
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
        return run

    async def cancel_active_runs_for_flows(
        self,
        flow_ids: list[UUID],
        reason: str,
    ) -> int:
        if not flow_ids:
            return 0
        result = await self.session.execute(
            select(Run).where(
                Run.flow_id.in_(flow_ids),
                Run.status.in_(["pending", "running"]),
            )
        )
        runs = list(result.scalars().all())
        if not runs:
            return 0

        now = datetime.now(UTC)
        for run in runs:
            self._revoke_task(run.celery_task_id)
            run.status = "cancelled"
            run.error_message = reason
            run.completed_at = now
            run.celery_task_id = None
        await self.session.flush()
        return len(runs)

    async def has_active_run(
        self,
        flow_id: UUID,
        finalize_stale: bool = True,
        auto_commit: bool = True,
    ) -> bool:
        if finalize_stale:
            await self.mark_stale_pending_runs(flow_id, auto_commit=auto_commit)
            await self.mark_stale_running_runs(flow_id, auto_commit=auto_commit)
        result = await self.session.execute(
            select(Run).where(
                Run.flow_id == flow_id,
                Run.status.in_(["pending", "running"]),
            )
        )
        return result.scalar_one_or_none() is not None

    async def mark_stale_pending_runs(self, flow_id: UUID, auto_commit: bool = True) -> int:
        stale_before = datetime.now(UTC) - timedelta(minutes=settings.stale_pending_run_minutes)
        result = await self.session.execute(
            select(Run).where(
                Run.flow_id == flow_id,
                Run.status == "pending",
                Run.created_at < stale_before,
            )
        )
        stale_runs = list(result.scalars().all())
        if not stale_runs:
            return 0

        for run in stale_runs:
            run.status = "failed"
            run.error_message = (
                "Запуск помечен как неуспешный: задача не была обработана worker в ожидаемое время."
            )
            run.completed_at = datetime.now(UTC)
        flow = await self.session.get(Flow, flow_id)
        if flow and flow.status == "running":
            flow.status = "failed"
            flow.status_reason = (
                "Поток помечен как неуспешный: активный запуск устарел и был остановлен."
            )
            flow.pause_requested = False
        if auto_commit:
            await self.session.commit()
        return len(stale_runs)

    async def mark_stale_running_runs(self, flow_id: UUID, auto_commit: bool = True) -> int:
        grace_seconds = settings.meltano_command_timeout_seconds + 600
        stale_before = datetime.now(UTC) - timedelta(seconds=grace_seconds)
        result = await self.session.execute(
            select(Run).where(
                Run.flow_id == flow_id,
                Run.status == "running",
                Run.started_at.is_not(None),
                Run.started_at < stale_before,
            )
        )
        stale_runs = list(result.scalars().all())
        if not stale_runs:
            return 0

        for run in stale_runs:
            run.status = "failed"
            run.error_message = (
                "Запуск помечен как неуспешный: превышено допустимое время выполнения."
            )
            run.completed_at = datetime.now(UTC)
        flow = await self.session.get(Flow, flow_id)
        if flow and flow.status == "running":
            flow.status = "failed"
            flow.status_reason = (
                "Поток помечен как неуспешный: превышено допустимое время выполнения запуска."
            )
            flow.pause_requested = False
        if auto_commit:
            await self.session.commit()
        return len(stale_runs)
