from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.source_service import SourceService


def test_validate_jira_source_accepts_username_without_email() -> None:
    SourceService._validate_source(
        source_type="jira",
        host="https://sberworks.ru/jira",
        port=443,
        database="",
        username="tsarev.n",
        password="token",
        require_password=True,
    )


def test_validate_jira_basic_password_accepts_username() -> None:
    SourceService._validate_source(
        source_type="jira",
        host="https://sberworks.ru/jira",
        port=443,
        database="",
        username="tsarev.n",
        password="secret",
        require_password=True,
        jira_auth_type="basic_password",
    )


def test_validate_jira_source_requires_username() -> None:
    with pytest.raises(ValueError, match="Логин Jira обязателен"):
        SourceService._validate_source(
            source_type="jira",
            host="https://sberworks.ru/jira",
            port=443,
            database="",
            username="",
            password="token",
            require_password=True,
        )


def test_validate_jira_pat_bearer_allows_empty_username() -> None:
    SourceService._validate_source(
        source_type="jira",
        host="https://sberworks.ru/jira",
        port=443,
        database="",
        username="",
        password="token",
        require_password=True,
        jira_auth_type="pat_bearer",
    )


def test_normalize_legacy_basic_alias_to_basic_token() -> None:
    assert SourceService._normalize_jira_auth_type("basic") == "basic_token"


class _DummyResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return list(self._rows)


class _DummySession:
    def __init__(self):
        self.deleted = []
        self.committed = False

    async def execute(self, _query):
        return _DummyResult([])

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_delete_source_soft_delete_marks_deleted_at() -> None:
    session = _DummySession()
    service = SourceService(session)
    source = SimpleNamespace(
        id=uuid4(),
        source_type="postgres",
        deleted_at=None,
    )

    async def _fake_get_source(_source_id):
        return source

    service.get_source = _fake_get_source  # type: ignore[method-assign]

    deleted = await service.delete_source(source.id, hard_delete=False, auto_commit=True)

    assert deleted is True
    assert isinstance(source.deleted_at, datetime)
    assert source.deleted_at.tzinfo == UTC
    assert session.deleted == []
    assert session.committed is True


@pytest.mark.asyncio
async def test_delete_source_hard_delete_removes_record() -> None:
    session = _DummySession()
    service = SourceService(session)
    source = SimpleNamespace(
        id=uuid4(),
        source_type="postgres",
        deleted_at=None,
    )

    async def _fake_get_source(_source_id):
        return source

    service.get_source = _fake_get_source  # type: ignore[method-assign]

    deleted = await service.delete_source(source.id, hard_delete=True, auto_commit=True)

    assert deleted is True
    assert source.deleted_at is None
    assert session.deleted == [source]
    assert session.committed is True
