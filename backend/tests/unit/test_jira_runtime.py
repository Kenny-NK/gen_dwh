from src.services.jira_loader import _prepare_rows, _resolve_upsert_column
from src.services.source_service import SourceService


def test_build_jira_extraction_config_sets_runtime_engine_for_basic() -> None:
    payload = SourceService._build_jira_extraction_config(None, jira_auth_type="basic_token")

    assert payload["auth_type"] == "basic_token"
    assert payload["runtime_engine"] == "meltano"


def test_build_jira_extraction_config_sets_runtime_engine_for_basic_password() -> None:
    payload = SourceService._build_jira_extraction_config(None, jira_auth_type="basic_password")

    assert payload["auth_type"] == "basic_password"
    assert payload["runtime_engine"] == "meltano"


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
