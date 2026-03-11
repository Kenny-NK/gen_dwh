import asyncio

from src.services import jira_loader as jira_loader_module
from src.services.jira_loader import _prepare_issue_rows, _prepare_rows, _resolve_upsert_column, run_jira_to_postgres
from src.services.source_service import SourceService


def test_build_jira_extraction_config_sets_runtime_engine_for_basic() -> None:
    payload = SourceService._build_jira_extraction_config(None, jira_auth_type="basic_token")

    assert payload["auth_type"] == "basic_token"
    assert payload["runtime_engine"] == "native"


def test_build_jira_extraction_config_sets_runtime_engine_for_basic_password() -> None:
    payload = SourceService._build_jira_extraction_config(None, jira_auth_type="basic_password")

    assert payload["auth_type"] == "basic_password"
    assert payload["runtime_engine"] == "native"


def test_build_jira_extraction_config_sets_runtime_engine_for_pat() -> None:
    payload = SourceService._build_jira_extraction_config(None, jira_auth_type="pat_bearer")

    assert payload["auth_type"] == "pat_bearer"
    assert payload["runtime_engine"] == "native"


def test_prepare_rows_tracks_max_cursor_and_record_id() -> None:
    columns, rows, max_cursor = _prepare_rows(
        [
            {"id": "1", "updated": "2026-03-01T00:00:00Z", "summary": "A"},
            {"id": "2", "updated": "2026-03-02T00:00:00Z", "summary": "B"},
        ],
        "updated",
    )

    assert "id" in columns
    assert "updated" in columns
    assert rows[0]["_record_id"] == "1"
    assert max_cursor == "2026-03-02T00:00:00Z"


def test_prepare_rows_flattens_nested_objects_into_columns() -> None:
    columns, rows, _ = _prepare_rows(
        [
            {
                "id": "1",
                "summary": "Task",
                "project": {"key": "DWHTOT", "name": "dwhtot"},
                "status": {"name": "Done", "statusCategory": {"name": "Completed"}},
            }
        ],
        "updated",
    )

    assert "project_key" in columns
    assert "project_name" in columns
    assert "status_name" in columns
    assert "status_statuscategory_name" in columns
    assert "project" not in columns
    assert rows[0]["project_key"] == "DWHTOT"
    assert rows[0]["status_name"] == "Done"


def test_resolve_upsert_column_prefers_primary_key() -> None:
    upsert_column = _resolve_upsert_column(
        {"stream": "issues", "replication_key": "updated"},
        "issues",
        ["id", "updated", "summary"],
        None,
    )

    assert upsert_column == "id"


def test_resolve_upsert_column_prefers_issue_id_over_replication_key_for_normalized_issues() -> None:
    upsert_column = _resolve_upsert_column(
        {"stream": "issues", "replication_key": "updated"},
        "issues",
        ["issue_id", "issue_key", "updated", "summary"],
        None,
    )

    assert upsert_column == "issue_id"


def test_prepare_issue_rows_normalizes_fields_into_stable_columns() -> None:
    columns, rows, max_cursor = _prepare_issue_rows(
        [
            {
                "id": "10001",
                "key": "DWHTOT-1",
                "fields": {
                    "summary": "Implement Jira connector",
                    "status": {"name": "Done", "statusCategory": {"name": "Completed"}},
                    "issuetype": {"name": "Task"},
                    "project": {"id": "200", "key": "DWHTOT", "name": "Platform"},
                    "created": "2026-03-01T12:00:00.000+0000",
                    "updated": "2026-03-02T12:00:00.000+0000",
                    "resolved": "2026-03-03T12:00:00.000+0000",
                    "reporter": {"accountId": "rep-1", "displayName": "Reporter"},
                    "assignee": {"accountId": "ass-1", "displayName": "Assignee"},
                    "priority": {"name": "High"},
                    "resolution": {"name": "Done"},
                    "labels": ["jira", "backend"],
                    "components": [{"name": "api"}],
                    "fixVersions": [{"name": "1.0.0"}],
                    "parent": {"key": "DWHTOT-0"},
                },
            }
        ],
        "updated",
    )

    assert "issue_id" in columns
    assert "issue_key" in columns
    assert "status_name" in columns
    assert "fields_raw" in columns
    assert rows[0]["issue_id"] == "10001"
    assert rows[0]["issue_key"] == "DWHTOT-1"
    assert rows[0]["status_name"] == "Done"
    assert rows[0]["project_key"] == "DWHTOT"
    assert rows[0]["_record_id"] == "10001"
    assert max_cursor == "2026-03-02T12:00:00.000+0000"


def test_run_jira_to_postgres_supports_basic_password_and_target_table_names(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyJiraService:
        def __init__(self, base_url: str, username: str, password: str, *, auth_type: str, **kwargs) -> None:
            captured["auth_type"] = auth_type
            captured["base_url"] = base_url
            captured["username"] = username

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def extract_records(self, **kwargs):
            captured["streams"] = kwargs["streams"]
            return {
                "issues": [
                    {
                        "id": "10001",
                        "key": "DWHTOT-1",
                        "fields": {
                            "summary": "Implement Jira connector",
                            "status": {"name": "Done", "statusCategory": {"name": "Completed"}},
                            "issuetype": {"name": "Task"},
                            "project": {"id": "200", "key": "DWHTOT", "name": "Platform"},
                            "updated": "2026-03-02T12:00:00.000+0000",
                        },
                    },
                    {
                        "id": "10002",
                        "key": "DWHTOT-2",
                        "fields": {
                            "summary": "Implement Jira connector 2",
                            "status": {"name": "Done", "statusCategory": {"name": "Completed"}},
                            "issuetype": {"name": "Task"},
                            "project": {"id": "200", "key": "DWHTOT", "name": "Platform"},
                            "updated": "2026-03-03T12:00:00.000+0000",
                        },
                    },
                ]
            }

    class DummyConnection:
        async def close(self) -> None:
            return None

    async def fake_connect(**kwargs):
        return DummyConnection()

    async def fake_store_stream_records(
        conn,
        target_schema,
        target_table,
        table_spec,
        records,
        *,
        write_mode,
        global_upsert_key,
        progress_callback=None,
    ):
        captured["target_schema"] = target_schema
        captured["target_table"] = target_table
        captured["record_count"] = len(records)
        if progress_callback:
            await progress_callback(len(records))
        return len(records), "2026-03-03T12:00:00.000+0000"

    monkeypatch.setattr(jira_loader_module, "JiraService", DummyJiraService)
    monkeypatch.setattr(jira_loader_module.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(jira_loader_module, "_store_stream_records", fake_store_stream_records)

    result = asyncio.run(
        run_jira_to_postgres(
            source_config={
                "host": "https://sberworks.ru/jira",
                "username": "tsarev.n",
                "password": "secret",
                "extraction_config": {
                    "auth_type": "basic_password",
                    "streams": ["issues"],
                    "query_mode": "jql",
                    "jql": 'project = DWHTOT AND status != "Cancelled"',
                },
            },
            target_config={"schema": "jira", "write_mode": "append"},
            tables=[{"stream": "issues", "table_name": "jira_issues", "replication_key": "updated"}],
        )
    )

    assert result.success is True
    assert result.records_processed == 2
    assert captured["auth_type"] == "basic_password"
    assert captured["streams"] == ["issues"]
    assert captured["target_schema"] == "jira"
    assert captured["target_table"] == "jira_issues"
    assert captured["record_count"] == 2
