import httpx

from src.services.jira_service import JiraService


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.atlassian.net/rest/api/3/myself")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError("error", request=request, response=response)


def test_classify_error_auth() -> None:
    classified = JiraService.classify_error(_http_status_error(401))
    assert classified.error_type == "auth"
    assert classified.message == "Authentication failed. Check your Jira auth type and username with password/token."


def test_pat_bearer_uses_authorization_header() -> None:
    service = JiraService(
        "https://example.atlassian.net",
        "",
        "token",
        auth_type="pat_bearer",
    )
    try:
        assert service.client.headers["Authorization"] == "Bearer token"
    finally:
        import asyncio

        asyncio.run(service.aclose())


def test_basic_password_uses_http_basic_auth() -> None:
    service = JiraService(
        "https://example.atlassian.net",
        "tsarev.n",
        "secret",
        auth_type="basic_password",
    )
    try:
        assert "Authorization" not in service.client.headers
        assert service.auth_type == "basic_password"
    finally:
        import asyncio

        asyncio.run(service.aclose())


def test_api_paths_use_rest_api_v2() -> None:
    assert JiraService._api_path("myself") == "/rest/api/2/myself"
    assert JiraService._api_path("/project/search") == "/rest/api/2/project/search"


def test_get_projects_accepts_legacy_project_list_payload() -> None:
    request = httpx.Request("GET", "https://example.local/rest/api/2/project")
    response = httpx.Response(
        200,
        request=request,
        json=[{"id": "1", "key": "DWH", "name": "Data Warehouse", "lead": {"displayName": "Lead"}}],
    )

    class DummyService(JiraService):
        async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
            assert method == "GET"
            assert path in {"project/search", "project"}
            if path == "project/search":
                raise httpx.HTTPStatusError("not found", request=request, response=httpx.Response(404, request=request))
            return response

    service = DummyService("https://example.local", "", "token")
    try:
        import asyncio

        projects = asyncio.run(service.get_projects())
    finally:
        import asyncio

        asyncio.run(service.aclose())

    assert len(projects) == 1
    assert projects[0].key == "DWH"


def test_users_preview_falls_back_to_username_search() -> None:
    request = httpx.Request("GET", "https://example.local/rest/api/2/user/search")
    response = httpx.Response(
        200,
        request=request,
        json=[{"accountId": "1", "displayName": "Test User"}],
    )

    class DummyService(JiraService):
        async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
            assert method == "GET"
            assert path == "user/search"
            params = kwargs.get("params", {})
            if "query" in params:
                raise httpx.HTTPStatusError("bad request", request=request, response=httpx.Response(400, request=request))
            assert params["username"] == "tsarev.n"
            return response

    service = DummyService("https://example.local", "tsarev.n", "token")
    try:
        import asyncio

        users = asyncio.run(service._get_users_preview_records(50))
    finally:
        import asyncio

        asyncio.run(service.aclose())

    assert len(users) == 1
    assert users[0]["accountId"] == "1"


def test_users_preview_returns_empty_when_endpoint_is_unsupported() -> None:
    request = httpx.Request("GET", "https://example.local/rest/api/2/user/search")

    class DummyService(JiraService):
        async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
            raise httpx.HTTPStatusError("bad request", request=request, response=httpx.Response(400, request=request))

    service = DummyService("https://example.local", "", "token", auth_type="pat_bearer")
    try:
        import asyncio

        users = asyncio.run(service._get_users_preview_records(50))
    finally:
        import asyncio

        asyncio.run(service.aclose())

    assert users == []


def test_classify_error_network() -> None:
    request = httpx.Request("GET", "https://example.atlassian.net")
    classified = JiraService.classify_error(httpx.ConnectError("down", request=request))
    assert classified.error_type == "network"


def test_classify_error_tls_certificate_failure() -> None:
    request = httpx.Request("GET", "https://example.atlassian.net")
    classified = JiraService.classify_error(
        httpx.ConnectError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain",
            request=request,
        )
    )
    assert classified.error_type == "network"
    assert classified.message == "TLS certificate validation failed while connecting to Jira."


def test_resolve_stream_dependencies() -> None:
    service = JiraService("https://example.atlassian.net", "user@example.com", "token")
    try:
        resolved = service.resolve_stream_dependencies(["worklogs"])
    finally:
        import asyncio

        asyncio.run(service.aclose())

    assert "issues" in resolved
    assert "worklogs" in resolved


def test_parse_singer_preview_output() -> None:
    stdout = "\n".join(
        [
            '{"type":"SCHEMA","stream":"issues","schema":{"type":"object","properties":{"id":{"type":"string"}}}}',
            '{"type":"RECORD","stream":"issues","record":{"id":"1","key":"ABC-1"}}',
        ]
    )
    parsed = JiraService.parse_singer_preview_output(stdout)
    assert parsed["schema"]["issues"]["type"] == "object"
    assert parsed["records"]["issues"][0]["id"] == "1"


def test_split_jql_ordering_extracts_order_by() -> None:
    filters, ordering = JiraService._split_jql_ordering(
        'project = DWHTOT AND status != "Cancelled" ORDER BY created DESC'
    )

    assert filters == 'project = DWHTOT AND status != "Cancelled"'
    assert ordering == "ORDER BY created DESC"


def test_build_issue_jql_preserves_single_order_by() -> None:
    service = JiraService("https://example.atlassian.net", "user@example.com", "token")
    try:
        query = service.build_issue_jql(
            jql='project = DWHTOT AND status != "Cancelled" ORDER BY created DESC',
        )
    finally:
        import asyncio

        asyncio.run(service.aclose())

    assert query == '(project = DWHTOT AND status != "Cancelled") ORDER BY created DESC'


def test_resolve_issue_query_inputs_uses_only_jql_mode_filters() -> None:
    resolved = JiraService.resolve_issue_query_inputs(
        query_mode="jql",
        project_keys=["DWHTOT"],
        jql='project = GEOPR ORDER BY created DESC',
        replication_key="updated",
    )

    assert resolved["query_mode"] == "jql"
    assert resolved["project_keys"] == []
    assert resolved["jql"] == 'project = GEOPR ORDER BY created DESC'
    assert resolved["start_date"] is None
    assert resolved["replication_key"] is None


def test_resolve_issue_query_inputs_uses_basic_filters_without_jql() -> None:
    resolved = JiraService.resolve_issue_query_inputs(
        query_mode="basic",
        project_keys=["DWHTOT"],
        jql='project = GEOPR ORDER BY created DESC',
        replication_key="created",
    )

    assert resolved["query_mode"] == "basic"
    assert resolved["project_keys"] == ["DWHTOT"]
    assert resolved["jql"] is None
    assert resolved["replication_key"] == "created"


def test_preview_records_normalizes_issues_and_exposes_columns() -> None:
    request = httpx.Request("GET", "https://example.local/rest/api/2/search")
    response = httpx.Response(
        200,
        request=request,
        json={
            "issues": [
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
                    },
                }
            ]
        },
    )

    class DummyService(JiraService):
            async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
                assert method == "GET"
                assert path == "search"
                params = kwargs.get("params", {})
                assert params["jql"] == '(project = DWHTOT) ORDER BY created DESC'
                assert "summary" in params["fields"]
                assert "resolved" in params["fields"]
                return response

    service = DummyService("https://example.local", "user", "token")
    try:
        import asyncio

        preview = asyncio.run(
            service.preview_records(
                streams=["issues"],
                query_mode="jql",
                jql='project = DWHTOT ORDER BY created DESC',
            )
        )
    finally:
        import asyncio

        asyncio.run(service.aclose())

    assert preview["effective_query_mode"] == "jql"
    assert preview["effective_jql"] == '(project = DWHTOT) ORDER BY created DESC'
    assert preview["records"]["issues"][0]["issue_key"] == "DWHTOT-1"
    assert preview["columns_by_stream"]["issues"][0] == "issue_id"
    assert preview["schema_by_stream"]["issues"]["schema"]["properties"]["issue_key"]["type"] == ["string", "null"]


def test_classify_error_uses_jira_error_message_for_bad_request() -> None:
    request = httpx.Request("GET", "https://example.local/rest/api/2/search")
    response = httpx.Response(
        400,
        request=request,
        json={"errorMessages": ["Error in the JQL Query: Expecting operator but got 'ORDER'."], "errors": {}},
    )
    classified = JiraService.classify_error(
        httpx.HTTPStatusError("bad request", request=request, response=response)
    )

    assert classified.error_type == "config"
    assert "Error in the JQL Query" in classified.message
