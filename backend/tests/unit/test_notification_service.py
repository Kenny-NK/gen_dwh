from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.notification_service import NotificationService


class _Result:
    def __init__(self, rowcount: int = 0, rows=None):
        self.rowcount = rowcount
        self._rows = list(rows or [])

    def one_or_none(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _DummySession:
    def __init__(self, *, rowcount: int = 0):
        self.rowcount = rowcount
        self.added = []
        self.flush_calls = 0
        self.commit_calls = 0
        self.execute_calls = 0
        self._next_results = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def commit(self) -> None:
        self.commit_calls += 1

    async def execute(self, _query):
        self.execute_calls += 1
        if self._next_results:
            return self._next_results.pop(0)
        return _Result(self.rowcount)


@pytest.mark.asyncio
async def test_create_notification_skips_commit_when_disabled() -> None:
    session = _DummySession()
    service = NotificationService(session)

    notification = await service.create_notification(
        type="info",
        title="Test",
        message="Body",
        user_id=uuid4(),
        auto_commit=False,
    )

    assert notification in session.added
    assert session.flush_calls == 1
    assert session.commit_calls == 0


@pytest.mark.asyncio
async def test_mark_read_skips_commit_when_disabled() -> None:
    session = _DummySession(rowcount=1)
    session._next_results = [_Result(rows=[SimpleNamespace(is_broadcast=False, user_id=uuid4())]), _Result(rowcount=1)]
    service = NotificationService(session)

    updated = await service.mark_read(uuid4(), uuid4(), auto_commit=False)

    assert updated is True
    assert session.execute_calls == 2
    assert session.commit_calls == 0


@pytest.mark.asyncio
async def test_mark_all_read_skips_commit_when_disabled() -> None:
    session = _DummySession()
    session._next_results = [_Result(rowcount=0), _Result(rows=[])]
    service = NotificationService(session)

    await service.mark_all_read(uuid4(), auto_commit=False)

    assert session.execute_calls == 2
    assert session.commit_calls == 0
