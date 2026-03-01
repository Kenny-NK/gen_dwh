"""Schedule service with cron validation (T080, T087)."""

from datetime import UTC, datetime
from uuid import UUID

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.schedule import Schedule


class ScheduleService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_schedule(self, flow_id: UUID) -> Schedule | None:
        result = await self.session.execute(
            select(Schedule).where(Schedule.flow_id == flow_id)
        )
        return result.scalar_one_or_none()

    async def upsert_schedule(
        self,
        flow_id: UUID,
        schedule_type: str,
        cron_expression: str | None = None,
        interval_minutes: int | None = None,
        timezone: str = "Europe/Moscow",
        max_retries: int = 5,
        timeout_minutes: int = 120,
        created_by: UUID | None = None,
    ) -> Schedule:
        if schedule_type not in {"cron", "interval", "manual"}:
            raise ValueError("schedule_type must be one of: cron, interval, manual")
        if schedule_type == "cron" and not cron_expression:
            raise ValueError("cron_expression is required for cron schedules")
        if schedule_type == "interval" and not interval_minutes:
            raise ValueError("interval_minutes is required for interval schedules")

        schedule = await self.get_schedule(flow_id)

        if schedule:
            schedule.schedule_type = schedule_type
            schedule.cron_expression = cron_expression
            schedule.interval_minutes = interval_minutes
            schedule.timezone = timezone
            schedule.max_retries = max_retries
            schedule.timeout_minutes = timeout_minutes
        else:
            schedule = Schedule(
                flow_id=flow_id,
                schedule_type=schedule_type,
                cron_expression=cron_expression,
                interval_minutes=interval_minutes,
                timezone=timezone,
                max_retries=max_retries,
                timeout_minutes=timeout_minutes,
                created_by=created_by,
            )
            self.session.add(schedule)

        # Calculate next run
        if schedule_type == "cron" and cron_expression:
            schedule.next_run_at = self._get_next_cron_time(cron_expression)
        elif schedule_type == "interval" and interval_minutes:
            from datetime import timedelta

            schedule.next_run_at = datetime.now(UTC) + timedelta(minutes=interval_minutes)
        else:
            schedule.next_run_at = None

        await self.session.flush()
        await self.session.commit()
        return schedule

    async def delete_schedule(self, flow_id: UUID) -> bool:
        schedule = await self.get_schedule(flow_id)
        if not schedule:
            return False
        await self.session.delete(schedule)
        await self.session.commit()
        return True

    async def list_schedules(
        self,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Schedule]:
        query = select(Schedule)
        if is_active is not None:
            query = query.where(Schedule.is_active == is_active)
        query = query.order_by(Schedule.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    def validate_cron(expression: str) -> dict:
        """Validate a cron expression and return next 5 scheduled times (T087)."""
        try:
            cron = croniter(expression)
            next_times = [cron.get_next(datetime).isoformat() for _ in range(5)]
            return {"valid": True, "next_times": next_times}
        except (ValueError, KeyError) as e:
            return {"valid": False, "error": str(e)}

    @staticmethod
    def _get_next_cron_time(expression: str) -> datetime:
        return croniter(expression).get_next(datetime)
