"""Normalization helpers for Jira issue preview/load payloads."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


ISSUE_API_FIELDS: tuple[str, ...] = (
    "summary",
    "status",
    "issuetype",
    "project",
    "created",
    "updated",
    "resolved",
    "reporter",
    "assignee",
    "priority",
    "resolution",
    "labels",
    "components",
    "fixVersions",
    "parent",
)

ISSUE_COLUMN_ORDER: tuple[str, ...] = (
    "issue_id",
    "issue_key",
    "summary",
    "status_name",
    "status_category_name",
    "issue_type_name",
    "project_id",
    "project_key",
    "project_name",
    "created",
    "updated",
    "resolved",
    "reporter_account_id",
    "reporter_display_name",
    "assignee_account_id",
    "assignee_display_name",
    "priority_name",
    "resolution_name",
    "labels",
    "components",
    "fix_versions",
    "parent_issue_key",
    "fields_raw",
)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text or None


def _extract_name_list(values: Any) -> str | None:
    if not isinstance(values, list):
        return _stringify(values)
    normalized: list[str] = []
    for value in values:
        if isinstance(value, dict):
            normalized.append(str(value.get("name") or value.get("value") or "").strip())
        else:
            normalized.append(str(value).strip())
    compact = [item for item in normalized if item]
    return _stringify(compact)


def normalize_issue_record(issue: dict[str, Any]) -> dict[str, str | None]:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
    status_category = (
        status.get("statusCategory")
        if isinstance(status.get("statusCategory"), dict)
        else {}
    )
    issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
    project = fields.get("project") if isinstance(fields.get("project"), dict) else {}
    reporter = fields.get("reporter") if isinstance(fields.get("reporter"), dict) else {}
    assignee = fields.get("assignee") if isinstance(fields.get("assignee"), dict) else {}
    priority = fields.get("priority") if isinstance(fields.get("priority"), dict) else {}
    resolution = fields.get("resolution") if isinstance(fields.get("resolution"), dict) else {}
    parent = fields.get("parent") if isinstance(fields.get("parent"), dict) else {}

    return {
        "issue_id": _stringify(issue.get("id")),
        "issue_key": _stringify(issue.get("key")),
        "summary": _stringify(fields.get("summary")),
        "status_name": _stringify(status.get("name")),
        "status_category_name": _stringify(status_category.get("name")),
        "issue_type_name": _stringify(issue_type.get("name")),
        "project_id": _stringify(project.get("id")),
        "project_key": _stringify(project.get("key")),
        "project_name": _stringify(project.get("name")),
        "created": _stringify(fields.get("created")),
        "updated": _stringify(fields.get("updated")),
        "resolved": _stringify(fields.get("resolved")),
        "reporter_account_id": _stringify(reporter.get("accountId")),
        "reporter_display_name": _stringify(reporter.get("displayName") or reporter.get("name")),
        "assignee_account_id": _stringify(assignee.get("accountId")),
        "assignee_display_name": _stringify(assignee.get("displayName") or assignee.get("name")),
        "priority_name": _stringify(priority.get("name")),
        "resolution_name": _stringify(resolution.get("name")),
        "labels": _extract_name_list(fields.get("labels")),
        "components": _extract_name_list(fields.get("components")),
        "fix_versions": _extract_name_list(fields.get("fixVersions")),
        "parent_issue_key": _stringify(parent.get("key")),
        "fields_raw": _stringify(fields),
    }


def issue_preview_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns = list(ISSUE_COLUMN_ORDER)
    seen = set(columns)
    for row in rows:
        for key in row.keys():
            if key not in seen:
                columns.append(key)
                seen.add(key)
    return columns


def issue_preview_schema() -> dict[str, Any]:
    properties = {column: {"type": ["string", "null"]} for column in ISSUE_COLUMN_ORDER}
    return {
        "stream_name": "issues",
        "schema": {
            "type": "object",
            "properties": properties,
        },
        "field_count": len(properties),
        "replication_key": "updated",
    }
