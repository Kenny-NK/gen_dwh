"""Jira API and metadata service."""

from __future__ import annotations

import json
from datetime import UTC, datetime
import re
from typing import Any

import httpx

from src.core.http import get_http_client_ssl_context
from src.schemas.jira import JiraErrorResponse, JiraProject, JiraStreamMetadata
from src.services.jira_issue_normalization import (
    ISSUE_API_FIELDS,
    issue_preview_columns,
    issue_preview_schema,
    normalize_issue_record,
)


_ORDER_BY_RE = re.compile(r"\border\s+by\b", re.IGNORECASE)


class JiraService:
    REST_API_BASE = "/rest/api/2"
    STREAMS: dict[str, JiraStreamMetadata] = {
        "issues": JiraStreamMetadata(
            name="issues",
            display_name="Issues",
            description="Jira issues and tickets",
            replication_method="INCREMENTAL",
            replication_keys=["updated"],
            primary_keys=["id"],
            field_count=45,
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "key": {"type": "string"},
                    "summary": {"type": "string"},
                    "status": {"type": "object"},
                    "project": {"type": "object"},
                    "created": {"type": "string", "format": "date-time"},
                    "updated": {"type": "string", "format": "date-time"},
                },
            },
        ),
        "projects": JiraStreamMetadata(
            name="projects",
            display_name="Projects",
            description="Jira projects",
            replication_method="FULL_TABLE",
            primary_keys=["id"],
            field_count=20,
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "key": {"type": "string"},
                    "name": {"type": "string"},
                    "projectTypeKey": {"type": "string"},
                },
            },
        ),
        "users": JiraStreamMetadata(
            name="users",
            display_name="Users",
            description="Jira users",
            replication_method="FULL_TABLE",
            primary_keys=["accountId"],
            field_count=15,
            schema={
                "type": "object",
                "properties": {
                    "accountId": {"type": "string"},
                    "displayName": {"type": "string"},
                    "emailAddress": {"type": ["string", "null"]},
                },
            },
        ),
        "worklogs": JiraStreamMetadata(
            name="worklogs",
            display_name="Worklogs",
            description="Time tracking entries",
            replication_method="INCREMENTAL",
            replication_keys=["updated"],
            primary_keys=["id"],
            parent_stream="issues",
            field_count=12,
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "issueId": {"type": "string"},
                    "started": {"type": "string", "format": "date-time"},
                    "updated": {"type": "string", "format": "date-time"},
                    "timeSpentSeconds": {"type": "integer"},
                },
            },
        ),
        "issue_comments": JiraStreamMetadata(
            name="issue_comments",
            display_name="Issue comments",
            description="Comments on Jira issues",
            replication_method="INCREMENTAL",
            replication_keys=["created"],
            primary_keys=["id"],
            parent_stream="issues",
            field_count=8,
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "body": {"type": ["string", "null"]},
                    "created": {"type": "string", "format": "date-time"},
                    "updated": {"type": "string", "format": "date-time"},
                },
            },
        ),
        "changelogs": JiraStreamMetadata(
            name="changelogs",
            display_name="Changelogs",
            description="Issue history changes",
            replication_method="INCREMENTAL",
            replication_keys=["created"],
            primary_keys=["id"],
            parent_stream="issues",
            field_count=10,
            schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "created": {"type": "string", "format": "date-time"},
                    "items": {"type": "array"},
                },
            },
        ),
    }

    def __init__(
        self,
        base_url: str,
        username: str,
        api_token: str | None = None,
        *,
        auth_type: str = "basic_token",
        timeout_seconds: float = 15.0,
    ):
        normalized_base_url = (base_url or "").rstrip("/")
        self.base_url = normalized_base_url
        self.username = username
        self.api_token = api_token or ""
        normalized_auth_type = str(auth_type or "").strip().lower()
        if normalized_auth_type == "pat_bearer":
            self.auth_type = "pat_bearer"
        elif normalized_auth_type == "basic_password":
            self.auth_type = "basic_password"
        else:
            self.auth_type = "basic_token"
        headers = {"Accept": "application/json"}
        client_kwargs: dict[str, Any] = {}
        if self.auth_type == "pat_bearer":
            if self.api_token:
                headers["Authorization"] = f"Bearer {self.api_token}"
        else:
            client_kwargs["auth"] = (username, self.api_token)
        self.client = httpx.AsyncClient(
            base_url=normalized_base_url,
            headers=headers,
            timeout=timeout_seconds,
            verify=get_http_client_ssl_context(),
            **client_kwargs,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> "JiraService":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    @staticmethod
    def classify_error(error: Exception) -> JiraErrorResponse:
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            response_payload: dict[str, Any] | None = None
            response_text = ""
            try:
                response_payload = error.response.json()
            except Exception:
                response_text = (error.response.text or "").strip()
            else:
                if isinstance(response_payload, dict):
                    error_messages = response_payload.get("errorMessages")
                    errors = response_payload.get("errors")
                    parts: list[str] = []
                    if isinstance(error_messages, list):
                        parts.extend(str(item).strip() for item in error_messages if str(item).strip())
                    if isinstance(errors, dict):
                        parts.extend(
                            f"{key}: {value}"
                            for key, value in errors.items()
                            if str(key).strip() and str(value).strip()
                        )
                    response_text = "; ".join(parts).strip()
            if status_code in (401, 403):
                return JiraErrorResponse(
                    message="Authentication failed. Check your Jira auth type and username with password/token.",
                    error_type="auth",
                    suggestion="Verify whether this Jira expects Basic auth with password/token or Bearer PAT, then retry with matching credentials.",
                )
            if status_code == 429:
                return JiraErrorResponse(
                    message="Jira API rate limit exceeded.",
                    error_type="runtime",
                    suggestion="Reduce batch size and retry later.",
                )
            if status_code in (400, 404):
                return JiraErrorResponse(
                    message=response_text or "Invalid Jira configuration or endpoint.",
                    error_type="config",
                    suggestion="Check Jira base URL and extraction settings.",
                )
            return JiraErrorResponse(
                message="Jira runtime error.",
                error_type="runtime",
                suggestion="Retry the operation or inspect Jira service status.",
            )

        if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
            message = str(error).lower()
            if "certificate verify failed" in message or "self-signed certificate" in message:
                return JiraErrorResponse(
                    message="TLS certificate validation failed while connecting to Jira.",
                    error_type="network",
                    suggestion="Add the corporate CA certificate to the backend trust bundle or fix the Jira certificate chain.",
                )
            return JiraErrorResponse(
                message="Network error while connecting to Jira.",
                error_type="network",
                suggestion="Verify base URL availability and outbound network access.",
            )

        return JiraErrorResponse(
            message="Unexpected Jira connector error.",
            error_type="runtime",
            suggestion="Retry and check backend logs.",
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = await self.client.request(method, self._api_path(path), **kwargs)
        response.raise_for_status()
        return response

    @classmethod
    def _api_path(cls, path: str) -> str:
        return f"{cls.REST_API_BASE}/{path.lstrip('/')}"

    async def validate_jira_credentials(self) -> dict[str, Any]:
        response = await self._request("GET", "myself")
        payload = response.json()
        return {
            "display_name": payload.get("displayName"),
            "account_id": payload.get("accountId"),
            "email_address": payload.get("emailAddress"),
        }

    async def get_projects(self) -> list[JiraProject]:
        try:
            response = await self._request(
                "GET",
                "project/search",
                params={"maxResults": 100},
            )
            payload = response.json()
            values = payload.get("values") if isinstance(payload, dict) else None
            raw_projects = values if isinstance(values, list) else []
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            response = await self._request("GET", "project")
            payload = response.json() if response.content else []
            raw_projects = payload if isinstance(payload, list) else []
        projects: list[JiraProject] = []
        for project in raw_projects:
            if not isinstance(project, dict):
                continue
            lead = project.get("lead") if isinstance(project.get("lead"), dict) else {}
            projects.append(
                JiraProject(
                    id=str(project.get("id") or ""),
                    key=str(project.get("key") or ""),
                    name=str(project.get("name") or ""),
                    lead_display_name=str(lead.get("displayName") or "") or None,
                    lead_account_id=str(lead.get("accountId") or "") or None,
                )
            )
        return [item for item in projects if item.id and item.key and item.name]

    def get_streams(self) -> list[JiraStreamMetadata]:
        return [self.STREAMS[key] for key in sorted(self.STREAMS.keys())]

    def get_stream_schema(self, name: str) -> dict[str, Any]:
        stream = self.STREAMS.get((name or "").strip().lower())
        if not stream:
            raise ValueError(f"Unknown Jira stream: {name}")
        return {
            "stream_name": stream.name,
            "schema": stream.stream_schema or {"type": "object", "properties": {}},
            "field_count": stream.field_count,
            "replication_key": stream.replication_keys[0] if stream.replication_keys else None,
        }

    def resolve_stream_dependencies(self, streams: list[str]) -> list[str]:
        normalized = [str(item).strip().lower() for item in streams if str(item).strip()]
        resolved: list[str] = []
        for stream_name in normalized:
            if stream_name not in self.STREAMS:
                continue
            parent = self.STREAMS[stream_name].parent_stream
            if parent and parent not in resolved:
                resolved.append(parent)
            if stream_name not in resolved:
                resolved.append(stream_name)
        if not resolved:
            resolved.append("issues")
        return resolved

    async def _get_users_preview_records(self, batch_size: int) -> list[dict[str, Any]]:
        limit = min(max(batch_size, 1), 100)
        fallback_params: list[dict[str, Any]] = [{"query": "", "maxResults": limit}]
        if self.username:
            fallback_params.append({"username": self.username, "maxResults": limit})
        fallback_params.append({"username": ".", "maxResults": limit})

        for index, params in enumerate(fallback_params):
            try:
                response = await self._request("GET", "user/search", params=params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (400, 404):
                    raise
                if index == len(fallback_params) - 1:
                    return []
                continue

            payload = response.json() if response.content else []
            return payload if isinstance(payload, list) else []

        return []

    @staticmethod
    def _format_jql_datetime(raw_value: datetime | str | None) -> str | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return None
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return text
        else:
            parsed = raw_value
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _split_jql_ordering(raw_jql: str | None) -> tuple[str | None, str | None]:
        text = str(raw_jql or "").strip()
        if not text:
            return None, None
        match = _ORDER_BY_RE.search(text)
        if not match:
            return text, None
        filters = text[: match.start()].strip()
        ordering = text[match.start() :].strip()
        return filters or None, ordering or None

    @staticmethod
    def resolve_issue_query_inputs(
        *,
        query_mode: str | None,
        project_keys: list[str] | None = None,
        jql: str | None = None,
        start_date: datetime | None = None,
        replication_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(query_mode or "").strip().lower()
        if normalized_mode == "jql":
            return {
                "query_mode": "jql",
                "project_keys": [],
                "jql": str(jql or "").strip() or None,
                "start_date": None,
                "replication_key": None,
            }
        return {
            "query_mode": "basic",
            "project_keys": [str(item).strip() for item in (project_keys or []) if str(item).strip()],
            "jql": None,
            "start_date": start_date,
            "replication_key": str(replication_key or "updated").strip() or "updated",
        }

    def build_issue_jql(
        self,
        *,
        project_keys: list[str] | None = None,
        jql: str | None = None,
        start_date: datetime | None = None,
        replication_key: str | None = None,
        cursor_value: str | None = None,
    ) -> str:
        jql_parts: list[str] = []
        user_filters, user_ordering = self._split_jql_ordering(jql)
        if project_keys:
            joined = ",".join(sorted({item.strip().upper() for item in project_keys if item.strip()}))
            if joined:
                jql_parts.append(f"project IN ({joined})")
        cursor_marker = self._format_jql_datetime(cursor_value or start_date)
        replication_field = str(replication_key or "updated").strip() or "updated"
        if cursor_marker and replication_field in {"updated", "created"}:
            jql_parts.append(f'{replication_field} >= "{cursor_marker}"')
        if user_filters:
            jql_parts.append(f"({user_filters})")
        filters_sql = " AND ".join(jql_parts)
        ordering_sql = user_ordering or "ORDER BY updated ASC"
        if not filters_sql:
            return user_ordering or "ORDER BY updated DESC"
        return f"{filters_sql} {ordering_sql}"

    async def search_issues(
        self,
        *,
        project_keys: list[str] | None = None,
        jql: str | None = None,
        query_mode: str | None = None,
        batch_size: int = 100,
        start_date: datetime | None = None,
        replication_key: str | None = None,
        cursor_value: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start_at = 0
        page_size = min(max(batch_size, 1), 100)
        effective = self.resolve_issue_query_inputs(
            query_mode=query_mode,
            project_keys=project_keys,
            jql=jql,
            start_date=start_date,
            replication_key=replication_key,
        )
        query = self.build_issue_jql(
            project_keys=effective["project_keys"],
            jql=effective["jql"],
            start_date=effective["start_date"],
            replication_key=effective["replication_key"],
            cursor_value=cursor_value,
        )

        while True:
            response = await self._request(
                "GET",
                "search",
                params={
                    "jql": query,
                    "startAt": start_at,
                    "maxResults": page_size,
                    "fields": ",".join((*ISSUE_API_FIELDS, "comment", "worklog")),
                },
            )
            payload = response.json() if response.content else {}
            issues = payload.get("issues") if isinstance(payload, dict) else []
            if not isinstance(issues, list) or not issues:
                break
            results.extend(issue for issue in issues if isinstance(issue, dict))
            total = int(payload.get("total") or 0) if isinstance(payload, dict) else 0
            start_at += len(issues)
            if total and start_at >= total:
                break
            if len(issues) < page_size:
                break
        return results

    async def get_users(self, batch_size: int = 100) -> list[dict[str, Any]]:
        limit = min(max(batch_size, 1), 1000)
        fallback_params: list[dict[str, Any]] = [{"query": "", "maxResults": limit}]
        if self.username:
            fallback_params.append({"username": self.username, "maxResults": limit})
        fallback_params.append({"username": ".", "maxResults": limit})

        for index, params in enumerate(fallback_params):
            try:
                response = await self._request("GET", "user/search", params=params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (400, 404):
                    raise
                if index == len(fallback_params) - 1:
                    return []
                continue
            payload = response.json() if response.content else []
            return payload if isinstance(payload, list) else []
        return []

    async def get_issue_comments(self, issue_key: str) -> list[dict[str, Any]]:
        start_at = 0
        comments: list[dict[str, Any]] = []
        while True:
            response = await self._request(
                "GET",
                f"issue/{issue_key}/comment",
                params={"startAt": start_at, "maxResults": 100},
            )
            payload = response.json() if response.content else {}
            values = payload.get("comments") if isinstance(payload, dict) else []
            if not isinstance(values, list) or not values:
                break
            comments.extend(item for item in values if isinstance(item, dict))
            total = int(payload.get("total") or 0) if isinstance(payload, dict) else 0
            start_at += len(values)
            if total and start_at >= total:
                break
            if len(values) < 100:
                break
        return comments

    async def get_issue_worklogs(self, issue_key: str) -> list[dict[str, Any]]:
        start_at = 0
        worklogs: list[dict[str, Any]] = []
        while True:
            response = await self._request(
                "GET",
                f"issue/{issue_key}/worklog",
                params={"startAt": start_at, "maxResults": 100},
            )
            payload = response.json() if response.content else {}
            values = payload.get("worklogs") if isinstance(payload, dict) else []
            if not isinstance(values, list) or not values:
                break
            worklogs.extend(item for item in values if isinstance(item, dict))
            total = int(payload.get("total") or 0) if isinstance(payload, dict) else 0
            start_at += len(values)
            if total and start_at >= total:
                break
            if len(values) < 100:
                break
        return worklogs

    async def get_issue_changelog(self, issue_key: str) -> list[dict[str, Any]]:
        start_at = 0
        changelogs: list[dict[str, Any]] = []
        while True:
            response = await self._request(
                "GET",
                f"issue/{issue_key}/changelog",
                params={"startAt": start_at, "maxResults": 100},
            )
            payload = response.json() if response.content else {}
            values = payload.get("values") if isinstance(payload, dict) else []
            if not isinstance(values, list) or not values:
                break
            changelogs.extend(item for item in values if isinstance(item, dict))
            total = int(payload.get("total") or 0) if isinstance(payload, dict) else 0
            start_at += len(values)
            if total and start_at >= total:
                break
            if len(values) < 100:
                break
        return changelogs

    async def extract_records(
        self,
        *,
        streams: list[str],
        project_keys: list[str] | None = None,
        jql: str | None = None,
        query_mode: str | None = None,
        batch_size: int = 100,
        start_date: datetime | None = None,
        incremental_enabled: bool = False,
        cursors_by_stream: dict[str, str | None] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        selected = self.resolve_stream_dependencies(streams)
        cursors = {str(key).strip().lower(): value for key, value in (cursors_by_stream or {}).items()}
        records: dict[str, list[dict[str, Any]]] = {stream_name: [] for stream_name in selected}

        if "projects" in selected:
            projects = await self.get_projects()
            if project_keys:
                allowed = {item.strip().upper() for item in project_keys if item.strip()}
                projects = [project for project in projects if project.key.upper() in allowed]
            records["projects"] = [project.model_dump() for project in projects]

        if "users" in selected:
            records["users"] = await self.get_users(batch_size=batch_size)

        if "issues" in selected:
            issue_replication_key = "updated"
            issue_cursor = cursors.get("issues") if incremental_enabled else None
            issues = await self.search_issues(
                project_keys=project_keys,
                jql=jql,
                query_mode=query_mode,
                batch_size=batch_size,
                start_date=start_date,
                replication_key=issue_replication_key,
                cursor_value=issue_cursor,
            )
            records["issues"] = issues

            wants_comments = "issue_comments" in selected
            wants_worklogs = "worklogs" in selected
            wants_changelogs = "changelogs" in selected

            if wants_comments:
                records["issue_comments"] = []
            if wants_worklogs:
                records["worklogs"] = []
            if wants_changelogs:
                records["changelogs"] = []

            for issue in issues:
                issue_id = str(issue.get("id") or "")
                issue_key = str(issue.get("key") or "")
                if not issue_key:
                    continue

                if wants_comments:
                    comments = await self.get_issue_comments(issue_key)
                    for comment in comments:
                        records["issue_comments"].append(
                            {
                                **comment,
                                "issueId": issue_id,
                                "issueKey": issue_key,
                            }
                        )

                if wants_worklogs:
                    worklogs = await self.get_issue_worklogs(issue_key)
                    for worklog in worklogs:
                        records["worklogs"].append(
                            {
                                **worklog,
                                "issueId": issue_id,
                                "issueKey": issue_key,
                            }
                        )

                if wants_changelogs:
                    changelog_items = await self.get_issue_changelog(issue_key)
                    for item in changelog_items:
                        records["changelogs"].append(
                            {
                                **item,
                                "issueId": issue_id,
                                "issueKey": issue_key,
                            }
                        )

        for stream_name in selected:
            records.setdefault(stream_name, [])
        return records

    async def preview_records(
        self,
        streams: list[str],
        project_keys: list[str] | None = None,
        jql: str | None = None,
        query_mode: str | None = None,
        batch_size: int = 50,
        start_date: datetime | None = None,
    ) -> dict[str, Any]:
        selected = self.resolve_stream_dependencies(streams)
        records: dict[str, list[dict[str, Any]]] = {}
        schema: dict[str, dict[str, Any]] = {}
        columns_by_stream: dict[str, list[str]] = {}
        rows_by_stream: dict[str, list[dict[str, Any]]] = {}

        if "projects" in selected:
            projects = await self.get_projects()
            if project_keys:
                allowed = {item.strip().upper() for item in project_keys if item.strip()}
                projects = [project for project in projects if project.key.upper() in allowed]
            records["projects"] = [project.model_dump() for project in projects[:batch_size]]
            schema["projects"] = self.get_stream_schema("projects")
            rows_by_stream["projects"] = records["projects"]
            columns_by_stream["projects"] = list(schema["projects"]["schema"].get("properties", {}).keys())

        if "issues" in selected:
            effective = self.resolve_issue_query_inputs(
                query_mode=query_mode,
                project_keys=project_keys,
                jql=jql,
                start_date=start_date,
            )
            query = self.build_issue_jql(
                project_keys=effective["project_keys"],
                jql=effective["jql"],
                start_date=effective["start_date"],
                replication_key=effective["replication_key"],
            )

            response = await self._request(
                "GET",
                "search",
                params={
                    "jql": query,
                    "maxResults": min(max(batch_size, 1), 100),
                    "fields": ",".join(ISSUE_API_FIELDS),
                },
            )
            payload = response.json() if response.content else {}
            issues = payload.get("issues") if isinstance(payload, dict) else []
            normalized_rows = [
                normalize_issue_record(issue)
                for issue in issues
                if isinstance(issue, dict)
            ] if isinstance(issues, list) else []
            records["issues"] = normalized_rows
            schema["issues"] = issue_preview_schema()
            rows_by_stream["issues"] = normalized_rows
            columns_by_stream["issues"] = issue_preview_columns(normalized_rows)

        if "users" in selected:
            records["users"] = await self._get_users_preview_records(batch_size)
            schema["users"] = self.get_stream_schema("users")
            rows_by_stream["users"] = records["users"]
            columns_by_stream["users"] = list(schema["users"]["schema"].get("properties", {}).keys())

        for stream_name in selected:
            if stream_name not in schema:
                schema[stream_name] = self.get_stream_schema(stream_name)
            records.setdefault(stream_name, [])
            rows_by_stream.setdefault(stream_name, records[stream_name])
            columns_by_stream.setdefault(
                stream_name,
                list(schema[stream_name]["schema"].get("properties", {}).keys()),
            )

        effective = self.resolve_issue_query_inputs(
            query_mode=query_mode,
            project_keys=project_keys,
            jql=jql,
            start_date=start_date,
        )

        return {
            "records": records,
            "schema": schema,
            "streams": selected,
            "record_count": sum(len(value) for value in records.values()),
            "effective_query_mode": effective["query_mode"],
            "effective_jql": self.build_issue_jql(
                project_keys=effective["project_keys"],
                jql=effective["jql"],
                start_date=effective["start_date"],
                replication_key=effective["replication_key"],
            )
            if "issues" in selected
            else None,
            "columns_by_stream": columns_by_stream,
            "rows_by_stream": rows_by_stream,
            "schema_by_stream": schema,
        }

    @staticmethod
    def parse_singer_preview_output(stdout_text: str) -> dict[str, Any]:
        """Extract sample records and schemas from Singer JSON lines."""
        records: dict[str, list[dict[str, Any]]] = {}
        schemas: dict[str, dict[str, Any]] = {}

        for line in stdout_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            message_type = str(payload.get("type") or "").upper()
            stream = str(payload.get("stream") or "").strip()
            if message_type == "SCHEMA" and stream:
                schemas[stream] = payload.get("schema") or {}
            if message_type == "RECORD" and stream:
                records.setdefault(stream, [])
                if len(records[stream]) < 100:
                    raw_record = payload.get("record")
                    if isinstance(raw_record, dict):
                        records[stream].append(raw_record)

        return {"records": records, "schema": schemas}
