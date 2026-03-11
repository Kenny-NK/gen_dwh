from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.schedule_service import ScheduleService
from src.services.scheduler import _next_schedule_run


def test_next_schedule_run_for_cron_uses_schedule_timezone() -> None:
    schedule = SimpleNamespace(
        schedule_type="cron",
        cron_expression="0 9 * * *",
        interval_minutes=None,
        timezone="Europe/Moscow",
    )
    base_time = datetime(2026, 3, 4, 0, 0, tzinfo=UTC)

    next_run = _next_schedule_run(schedule, base_time)

    assert next_run is not None
    assert next_run.tzinfo == UTC
    assert next_run == datetime(2026, 3, 4, 6, 0, tzinfo=UTC)


def test_next_schedule_run_for_interval_is_utc_delta() -> None:
    schedule = SimpleNamespace(
        schedule_type="interval",
        cron_expression=None,
        interval_minutes=30,
        timezone="Europe/Moscow",
    )
    base_time = datetime(2026, 3, 4, 10, 0, tzinfo=UTC)

    next_run = _next_schedule_run(schedule, base_time)

    assert next_run == base_time + timedelta(minutes=30)


def test_resolve_timezone_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Некорректный timezone"):
        ScheduleService._resolve_timezone("Invalid/Timezone")
