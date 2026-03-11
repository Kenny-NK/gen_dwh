from types import SimpleNamespace

from src.services.preview import PreviewService


def test_normalize_preview_rows_flattens_nested_objects() -> None:
    rows = PreviewService._normalize_preview_rows(
        [
            {
                "id": "1",
                "status": {"name": "Open", "statusCategory": {"name": "In Progress"}},
                "labels": ["backend", "jira"],
            }
        ]
    )

    assert rows == [
        {
            "id": "1",
            "status_name": "Open",
            "status_statuscategory_name": "In Progress",
            "labels": '["backend", "jira"]',
        }
    ]


def test_build_preview_columns_prefers_schema_then_row_keys() -> None:
    columns = PreviewService._build_preview_columns(
        rows=[{"id": "1", "extra": "x"}],
        schema_payload={
            "schema": {
                "properties": {
                    "id": {"type": "string"},
                    "summary": {"type": "string"},
                }
            }
        },
    )

    assert columns == ["id", "summary", "extra"]


def test_resolve_preview_mode_prefers_live_for_postgres_auto() -> None:
    flow = SimpleNamespace(
        preview_mode="auto",
        source=SimpleNamespace(source_type="postgres"),
    )

    requested_mode, resolved_mode = PreviewService._resolve_preview_mode(flow)

    assert requested_mode is None
    assert resolved_mode == "live"


def test_resolve_preview_mode_prefers_snapshot_for_jira_auto() -> None:
    flow = SimpleNamespace(
        preview_mode="auto",
        source=SimpleNamespace(source_type="jira"),
    )

    requested_mode, resolved_mode = PreviewService._resolve_preview_mode(flow)

    assert requested_mode is None
    assert resolved_mode == "snapshot"
