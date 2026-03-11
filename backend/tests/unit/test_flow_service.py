from uuid import uuid4

import pytest

from src.services.flow_service import FlowService


def test_resolve_requested_target_table_applies_prefix_for_jira_defaults() -> None:
    resolved = FlowService._resolve_requested_target_table(
        source_table="issues",
        requested_target_table="issues",
        table_prefix="jira_",
        source_type="jira",
    )

    assert resolved == "jira_issues"


def test_resolve_requested_target_table_keeps_custom_name_for_jira() -> None:
    resolved = FlowService._resolve_requested_target_table(
        source_table="issues",
        requested_target_table="custom_issues",
        table_prefix="jira_",
        source_type="jira",
    )

    assert resolved == "custom_issues"


class _DummySession:
    def __init__(self):
        self.items = []
        self.flush_calls = 0
        self.commit_calls = 0

    def add(self, item):
        self.items.append(item)

    async def flush(self):
        self.flush_calls += 1

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_enqueue_cleanup_jobs_deduplicates_targets() -> None:
    session = _DummySession()
    service = FlowService(session)
    related_entity_id = uuid4()

    jobs = await service.enqueue_cleanup_jobs(
        [
            ("analytics", "orders"),
            ("analytics", "orders"),
            ("analytics", "customers"),
        ],
        requested_by=uuid4(),
        related_entity_type="flow",
        related_entity_id=related_entity_id,
        auto_commit=False,
    )

    assert len(jobs) == 2
    assert [(job.target_schema, job.target_table) for job in jobs] == [
        ("analytics", "orders"),
        ("analytics", "customers"),
    ]
    assert all(job.related_entity_id == related_entity_id for job in jobs)
    assert session.flush_calls == 1
    assert session.commit_calls == 0
