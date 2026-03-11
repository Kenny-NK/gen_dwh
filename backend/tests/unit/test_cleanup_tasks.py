from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.models.cleanup_job import CleanupJob
from src.tasks.cleanup import (
    _cleanup_retry_delay,
    _for_each_tenant_session,
    _process_claimed_cleanup_jobs,
    _process_cleanup_jobs_summary,
)


class _DummySession:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


class _DummySessionManager:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.mark.asyncio
async def test_for_each_tenant_session_sets_schema_and_commits(monkeypatch) -> None:
    sessions = [_DummySession(), _DummySession()]
    schemas_seen: list[str] = []
    handled_sessions: list[_DummySession] = []

    async def fake_active_tenant_schemas() -> list[str]:
        return ["tenant_a", "tenant_b"]

    def fake_session_local():
        return _DummySessionManager(sessions.pop(0))

    async def fake_set_tenant_schema(session, schema_name: str) -> None:
        schemas_seen.append(schema_name)
        handled_sessions.append(session)

    async def fake_handler(session) -> None:
        handled_sessions.append(session)

    async def fake_ensure_tenant_schema_compatibility_once(schema_name: str) -> None:
        return None

    monkeypatch.setattr("src.tasks.cleanup._active_tenant_schemas", fake_active_tenant_schemas)
    monkeypatch.setattr("src.tasks.cleanup.SystemSessionLocal", fake_session_local)
    monkeypatch.setattr("src.tasks.cleanup.set_tenant_schema", fake_set_tenant_schema)
    monkeypatch.setattr(
        "src.tasks.cleanup.ensure_tenant_schema_compatibility_once",
        fake_ensure_tenant_schema_compatibility_once,
    )

    processed = await _for_each_tenant_session(fake_handler)

    assert processed == 2
    assert schemas_seen == ["tenant_a", "tenant_b"]
    assert all(session.committed for session in handled_sessions if hasattr(session, "committed"))


def test_cleanup_retry_delay_grows_and_is_capped() -> None:
    assert _cleanup_retry_delay(1).total_seconds() == 300
    assert _cleanup_retry_delay(2).total_seconds() == 600
    assert _cleanup_retry_delay(20).total_seconds() == 21600


class _CleanupSession:
    def __init__(self):
        self.flush_calls = 0
        self.commit_calls = 0

    async def flush(self):
        self.flush_calls += 1

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_process_claimed_cleanup_jobs_marks_success(monkeypatch) -> None:
    plans: list[list[tuple[str, str]]] = []

    class _DummyFlowService:
        def __init__(self, session):
            self.session = session

        async def execute_cleanup_plan(self, cleanup_plan):
            plans.append(cleanup_plan)

    class _DummyNotificationService:
        def __init__(self, session):
            self.session = session

        async def create_notification(self, **kwargs):
            raise AssertionError("notification should not be created on successful cleanup")

    async def fake_set_tenant_schema(session, schema_name: str) -> None:
        return None

    monkeypatch.setattr("src.tasks.cleanup.FlowService", _DummyFlowService)
    monkeypatch.setattr("src.tasks.cleanup.NotificationService", _DummyNotificationService)
    monkeypatch.setattr("src.tasks.cleanup.set_tenant_schema", fake_set_tenant_schema)

    session = _CleanupSession()
    job = CleanupJob(target_schema="analytics", target_table="orders")

    processed = await _process_claimed_cleanup_jobs(session, "tenant_a", [job])

    assert processed == 1
    assert plans == [[("analytics", "orders")]]
    assert job.status == "completed"
    assert job.attempt_count == 1
    assert job.completed_at is not None
    assert job.last_error is None
    assert session.flush_calls == 1
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_process_claimed_cleanup_jobs_marks_terminal_failure_and_notifies(monkeypatch) -> None:
    notifications: list[dict] = []

    class _DummyFlowService:
        def __init__(self, session):
            self.session = session

        async def execute_cleanup_plan(self, cleanup_plan):
            raise RuntimeError("drop failed")

    class _DummyNotificationService:
        def __init__(self, session):
            self.session = session

        async def create_notification(self, **kwargs):
            notifications.append(kwargs)
            return SimpleNamespace(id=uuid4())

    async def fake_set_tenant_schema(session, schema_name: str) -> None:
        return None

    monkeypatch.setattr("src.tasks.cleanup.FlowService", _DummyFlowService)
    monkeypatch.setattr("src.tasks.cleanup.NotificationService", _DummyNotificationService)
    monkeypatch.setattr("src.tasks.cleanup.set_tenant_schema", fake_set_tenant_schema)

    session = _CleanupSession()
    job = CleanupJob(
        target_schema="analytics",
        target_table="orders",
        requested_by=uuid4(),
        related_entity_type="flow",
        related_entity_id=uuid4(),
        attempt_count=7,
        max_attempts=8,
    )

    processed = await _process_claimed_cleanup_jobs(session, "tenant_a", [job])

    assert processed == 1
    assert job.status == "failed"
    assert job.attempt_count == 8
    assert job.completed_at is not None
    assert job.last_error == "drop failed"
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == job.requested_by
    assert notifications[0]["auto_commit"] is False
    assert session.flush_calls == 1
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_process_cleanup_jobs_summary_continues_after_tenant_failure(monkeypatch) -> None:
    async def fake_active_tenant_schemas() -> list[str]:
        return ["tenant_a", "tenant_b"]

    async def fake_process_cleanup_jobs_for_schema(schema_name: str) -> int:
        if schema_name == "tenant_a":
            raise RuntimeError("schema broken")
        return 3

    monkeypatch.setattr("src.tasks.cleanup._active_tenant_schemas", fake_active_tenant_schemas)
    monkeypatch.setattr(
        "src.tasks.cleanup._process_cleanup_jobs_for_schema",
        fake_process_cleanup_jobs_for_schema,
    )

    summary = await _process_cleanup_jobs_summary()

    assert summary["status"] == "degraded"
    assert summary["processed"] == 3
    assert summary["failed_schemas"] == [
        {"tenant_schema": "tenant_a", "error": "schema broken"}
    ]
