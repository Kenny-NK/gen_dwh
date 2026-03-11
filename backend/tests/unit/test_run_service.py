from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.run_service import RunService


class _DummyScalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)

    def one_or_none(self):
        return self._values[0] if self._values else None


class _DummyResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _DummyScalars(self._values)

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _DummySession:
    def __init__(self, runs, flow):
        self._runs = runs
        self._flow = flow
        self.commit_count = 0

    async def execute(self, _query):
        return _DummyResult(self._runs)

    async def get(self, _model, _flow_id):
        return self._flow

    async def commit(self):
        self.commit_count += 1


@pytest.mark.asyncio
async def test_mark_orphaned_pending_runs_marks_failed_and_commits() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        status="pending",
        celery_task_id=None,
        created_at=datetime.now(UTC) - timedelta(minutes=5),
        error_message=None,
        completed_at=None,
    )
    flow = SimpleNamespace(status="running", status_reason=None, pause_requested=True)
    session = _DummySession([run], flow)
    service = RunService(session)

    marked = await service.mark_orphaned_pending_runs(uuid4(), auto_commit=True)

    assert marked == 1
    assert run.status == "failed"
    assert "не была отправлена в очередь" in str(run.error_message)
    assert run.completed_at is not None
    assert flow.status == "failed"
    assert "не был отправлен в очередь" in str(flow.status_reason)
    assert flow.pause_requested is False
    assert session.commit_count == 1
