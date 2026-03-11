import asyncio

import pytest

from src.services.meltano import (
    _build_jira_issues_jql,
    _detect_jira_api_version,
    _extract_records_processed,
    _normalize_jira_domain,
    _patch_tap_jira_client,
    _patch_tap_jira_streams,
    generate_tap_jira_config,
    run_meltano_elt,
)


def test_extract_records_processed_from_json_metrics() -> None:
    stdout = '{"metrics":{"records_processed":42}}\n'
    stderr = ""
    assert _extract_records_processed(stdout, stderr) == 42


def test_extract_records_processed_from_text_logs() -> None:
    stdout = "job completed, records processed: 128"
    stderr = ""
    assert _extract_records_processed(stdout, stderr) == 128


def test_generate_tap_jira_config_supports_basic_password() -> None:
    config = generate_tap_jira_config(
        source_config={"host": "https://sberworks.ru/jira", "username": "tsarev.n", "password": "secret"},
        extraction_config={"auth_type": "basic_password", "streams": ["issues"]},
    )

    assert config["auth_type"] == "basic_password"
    assert config["domain"] == "sberworks.ru/jira"
    assert config["username"] == "tsarev.n"
    assert config["secret"] == "secret"


def test_generate_tap_jira_config_rejects_pat_bearer_for_meltano() -> None:
    with pytest.raises(ValueError, match="Bearer PAT"):
        generate_tap_jira_config(
            source_config={"host": "https://sberworks.ru/jira", "username": "", "password": "token"},
            extraction_config={"auth_type": "pat_bearer", "streams": ["issues"]},
        )


def test_normalize_jira_domain_preserves_context_path() -> None:
    assert _normalize_jira_domain("https://sberworks.ru/jira/") == "sberworks.ru/jira"


def test_build_jira_issues_jql_combines_projects_and_custom_filter() -> None:
    assert (
        _build_jira_issues_jql(["dwhtot", "bill"], 'statusCategory != Done ORDER BY updated DESC')
        == "(project in (BILL,DWHTOT)) AND ((statusCategory != Done ORDER BY updated DESC))"
    )


def test_detect_jira_api_version_for_onprem_basic_password() -> None:
    assert _detect_jira_api_version("https://sberworks.ru/jira", "basic_password") == "2"


def test_detect_jira_api_version_for_cloud_basic_token() -> None:
    assert _detect_jira_api_version("https://example.atlassian.net", "basic_token") == "3"


def test_patch_tap_jira_runtime_files(tmp_path) -> None:
    client_path = tmp_path / "client.py"
    client_path.write_text(
        """import sys

import requests.auth


class JiraStream:
    instance_name: str

    @property
    def url_base(self) -> str:
        cloud_id = self.config.get("cloud_id")
        if cloud_id:
            return f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
        domain = self.config["domain"]
        return f"https://{domain}/rest/api/3"

    @property
    def authenticator(self):
        return requests.auth.HTTPBasicAuth(
            password=self.config["api_token"],
            username=self.config["email"],
        )
""",
        encoding="utf-8",
    )
    streams_path = tmp_path / "streams.py"
    streams_path.write_text(
        '''"""Stream type classes for tap-jira."""\n\nimport functools\n\nclass IssueStream:\n    path = "/search/jql"\n    next_page_token_jsonpath = "$.nextPageToken"\n\n    def get_new_paginator(self) -> JSONPathPaginator:\n        """Return a new paginator for this stream."""\n        return JSONPathPaginator(jsonpath=self.next_page_token_jsonpath)\n\n    def get_url_params(self, context, next_page_token):\n        params = {}\n        if next_page_token:\n            params["nextPageToken"] = next_page_token\n        return params\n''',
        encoding="utf-8",
    )

    _patch_tap_jira_client(client_path)
    _patch_tap_jira_streams(streams_path)

    patched_client = client_path.read_text(encoding="utf-8")
    patched_streams = streams_path.read_text(encoding="utf-8")
    assert "_gendwh_jira_runtime_patch" in patched_client
    assert "import os" in patched_client
    assert "import requests" in patched_client
    assert "_gendwh_jira_runtime_patch" in patched_streams
    assert 'return "/search" if api_version == "2" else "/search/jql"' in patched_streams
    assert 'params["startAt"] = next_page_token' in patched_streams
    assert "_gendwh_relax_adf_nodes" in patched_streams
    assert "_gendwh_allow_issue_field_objects" in patched_streams
    assert 'schema_node["type"] = [*raw_type, "string"]' in patched_streams
    assert '_gendwh_allow_issue_field_objects(_gendwh_schema, ("security",))' in patched_streams


def test_run_meltano_elt_uses_force_for_jira(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            self.returncode = 0

        async def wait(self) -> int:
            return 0

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        return FakeProcess()

    import src.services.meltano as meltano_module

    monkeypatch.setattr(meltano_module, "MELTANO_PROJECT_DIR", tmp_path)
    external_bundle = tmp_path / "external-ca.pem"
    external_bundle.write_text("external-ca", encoding="utf-8")
    certifi_bundle = tmp_path / "certifi.pem"
    certifi_bundle.write_text("certifi-ca", encoding="utf-8")
    monkeypatch.setattr(meltano_module.settings, "external_ca_bundle_path", str(external_bundle))
    monkeypatch.setattr(meltano_module.certifi, "where", lambda: str(certifi_bundle))
    monkeypatch.setattr(meltano_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(meltano_module, "_ensure_tap_jira_runtime", lambda env: asyncio.sleep(0))

    result = asyncio.run(
        run_meltano_elt(
            source_config={
                "host": "https://sberworks.ru/jira",
                "username": "tsarev.n",
                "password": "secret",
                "extraction_config": {"auth_type": "basic_password", "streams": ["issues"]},
            },
            target_config={"schema": "public"},
            state_id="test-state",
            tables=[{"stream": "issues", "table": "issues"}],
            source_type="jira",
        )
    )

    assert result.success is True
    assert captured["cmd"] == (
        "meltano",
        "run",
        "--force",
        "--state-id-suffix",
        "test-state",
        "tap-jira",
        "target-postgres",
    )
    assert captured["env"]["REQUESTS_CA_BUNDLE"] == "/tmp/gendwh-ca-bundle.pem"
    assert captured["env"]["SSL_CERT_FILE"] == "/tmp/gendwh-ca-bundle.pem"
    assert captured["env"]["TAP_JIRA_API_VERSION"] == "2"
    assert captured["env"]["TAP_JIRA_CA_BUNDLE"] == "/tmp/gendwh-ca-bundle.pem"
