"""Meltano orchestration service (T075)."""

import asyncio
import certifi
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlparse

from sqlalchemy.engine import make_url

from src.core.config import settings


@dataclass
class MeltanoRunResult:
    success: bool
    records_processed: int = 0
    tables_processed: int = 0
    error_message: str | None = None
    state_file: str | None = None


MELTANO_PROJECT_DIR = Path(__file__).resolve().parents[2] / "meltano"
_RECORD_PATTERNS = [
    re.compile(r'"records_processed"\s*:\s*(\d+)'),
    re.compile(r"records[\s_-]*processed[^0-9]*(\d+)", re.IGNORECASE),
    re.compile(r'"records"\s*:\s*(\d+)'),
]
_meltano_failure_count = 0
_meltano_circuit_open_until = 0.0


def _target_defaults_from_settings() -> dict:
    url = make_url(settings.database_business_url)
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username or "gendwh",
        "password": url.password or "",
        "database": url.database or "gendwh_business",
    }


def _normalize_jira_domain(base_url: str) -> str:
    raw_url = str(base_url or "").strip()
    if not raw_url:
        return ""
    parsed = urlparse(raw_url)
    host = parsed.netloc.strip()
    path = parsed.path.rstrip("/")
    if not host:
        return raw_url.rstrip("/").removeprefix("https://").removeprefix("http://")
    if path and path != "/":
        return f"{host}{path}"
    return host


def _build_jira_issues_jql(project_keys: list[str] | None, raw_jql: str | None) -> str | None:
    clauses: list[str] = []
    normalized_keys = sorted({item.strip().upper() for item in (project_keys or []) if item and item.strip()})
    if normalized_keys:
        clauses.append(f"project in ({','.join(normalized_keys)})")

    normalized_jql = str(raw_jql or "").strip()
    if normalized_jql:
        clauses.append(f"({normalized_jql})")

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return " AND ".join(f"({clause})" for clause in clauses)


def _meltano_tls_env() -> dict[str, str]:
    bundle_path = str(settings.external_ca_bundle_path or "").strip()
    if not bundle_path:
        return {}
    merged_bundle_path = Path("/tmp/gendwh-ca-bundle.pem")
    external_bundle = Path(bundle_path)
    try:
        merged_bundle_path.write_text(
            Path(certifi.where()).read_text(encoding="utf-8")
            + "\n"
            + external_bundle.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        bundle_path = str(merged_bundle_path)
    except OSError:
        bundle_path = str(external_bundle)
    return {
        "REQUESTS_CA_BUNDLE": bundle_path,
        "SSL_CERT_FILE": bundle_path,
        "CURL_CA_BUNDLE": bundle_path,
        "PIP_CERT": bundle_path,
    }


def _detect_jira_api_version(base_url: str, auth_type: str | None = None) -> str:
    normalized_auth_type = str(auth_type or "").strip().lower()
    if normalized_auth_type == "basic_password":
        return "2"

    raw_url = str(base_url or "").strip()
    if not raw_url:
        return "3"

    parsed = urlparse(raw_url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if path or (host and not host.endswith(".atlassian.net")):
        return "2"
    return "3"


def _patch_tap_jira_client(client_path: Path) -> None:
    original = client_path.read_text(encoding="utf-8")
    patched = original

    patched = patched.replace("import requests.auth\n", "import os\n\nimport requests\nimport requests.auth\n")
    patched = patched.replace(
        """    @override
    @property
    def url_base(self) -> str:
        \"\"\"Returns base url.\"\"\"
        cloud_id = self.config.get(\"cloud_id\")
        if cloud_id:
            return f\"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3\"
        domain = self.config[\"domain\"]
        return f\"https://{domain}/rest/api/3\"

    @override
    @property
    def authenticator(self) -> _Auth:
""",
        """    @override
    @property
    def url_base(self) -> str:
        \"\"\"Returns base url.\"\"\"
        cloud_id = self.config.get(\"cloud_id\")
        if cloud_id:
            return f\"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3\"
        domain = self.config[\"domain\"]
        api_version = os.getenv(\"TAP_JIRA_API_VERSION\", \"3\").strip() or \"3\"
        return f\"https://{domain}/rest/api/{api_version}\"

    @property
    def requests_session(self) -> requests.Session:
        \"\"\"Return requests session with optional custom CA bundle.\"\"\"
        if not self._requests_session:
            self._requests_session = requests.Session()
        verify_bundle = os.getenv(\"TAP_JIRA_CA_BUNDLE\", \"\").strip()
        if verify_bundle:
            self._requests_session.verify = verify_bundle
        return self._requests_session

    @override
    @property
    def authenticator(self) -> _Auth:
""",
    )

    if patched == original:
        raise RuntimeError(f"Unable to patch tap-jira client runtime at {client_path}")

    if "_gendwh_jira_runtime_patch" not in patched:
        patched = "# _gendwh_jira_runtime_patch\n" + patched
    client_path.write_text(patched, encoding="utf-8")


def _patch_tap_jira_streams(streams_path: Path) -> None:
    original = streams_path.read_text(encoding="utf-8")
    patched = original

    patched = patched.replace("import functools\n", "import functools\nimport os\n")
    patched = patched.replace(
        '    path = "/search/jql"\n',
        """    @property
    def path(self) -> str:
        api_version = os.getenv("TAP_JIRA_API_VERSION", "3").strip() or "3"
        return "/search" if api_version == "2" else "/search/jql"
""",
    )
    patched = patched.replace(
        """    @override
    def get_new_paginator(self) -> JSONPathPaginator:
        \"\"\"Return a new paginator for this stream.\"\"\"
        return JSONPathPaginator(jsonpath=self.next_page_token_jsonpath)
""",
        """    @override
    def get_new_paginator(self):
        \"\"\"Return a new paginator for this stream.\"\"\"
        api_version = os.getenv("TAP_JIRA_API_VERSION", "3").strip() or "3"
        if api_version == "2":
            return super().get_new_paginator()
        return JSONPathPaginator(jsonpath=self.next_page_token_jsonpath)

    @override
    def get_next_page_token(
        self,
        response: requests.Response,
        previous_token: str | None,
    ) -> str | None:
        \"\"\"Return a token for identifying next page or None if no more pages.\"\"\"
        api_version = os.getenv("TAP_JIRA_API_VERSION", "3").strip() or "3"
        payload = response.json()
        if api_version != "2":
            return payload.get("nextPageToken")

        issues = payload.get("issues") or []
        start_at = int(payload.get("startAt", 0) or 0)
        total = int(payload.get("total", 0) or 0)
        next_token = start_at + len(issues)
        if not issues:
            return None
        if total and next_token >= total:
            return None
        return str(next_token)
""",
    )
    patched = patched.replace(
        """        if next_page_token:
            params["nextPageToken"] = next_page_token
""",
        """        if next_page_token:
            api_version = os.getenv("TAP_JIRA_API_VERSION", "3").strip() or "3"
            if api_version == "2":
                params["startAt"] = next_page_token
            else:
                params["nextPageToken"] = next_page_token
""",
    )

    relax_adf_patch = """
def _gendwh_relax_adf_nodes(schema_node):
    if isinstance(schema_node, dict):
        properties = schema_node.get("properties")
        if isinstance(properties, dict) and {"type", "version", "content"}.issubset(properties):
            raw_type = schema_node.get("type")
            if isinstance(raw_type, list):
                if "string" not in raw_type:
                    schema_node["type"] = [*raw_type, "string"]
            elif isinstance(raw_type, str):
                if raw_type != "string":
                    schema_node["type"] = [raw_type, "string"]
            else:
                schema_node["type"] = ["object", "string", "null"]

        for value in schema_node.values():
            _gendwh_relax_adf_nodes(value)
    elif isinstance(schema_node, list):
        for item in schema_node:
            _gendwh_relax_adf_nodes(item)


def _gendwh_allow_issue_field_objects(schema, field_names):
    field_properties = (
        schema.get("properties", {})
        .get("fields", {})
        .get("properties", {})
    )
    if not isinstance(field_properties, dict):
        return

    for field_name in field_names:
        field_schema = field_properties.get(field_name)
        if not isinstance(field_schema, dict):
            continue
        raw_type = field_schema.get("type")
        if isinstance(raw_type, list):
            normalized = list(raw_type)
            if "object" not in normalized:
                normalized.append("object")
            field_schema["type"] = normalized
        elif isinstance(raw_type, str):
            if raw_type != "object":
                field_schema["type"] = [raw_type, "object"]
        else:
            field_schema["type"] = ["string", "null", "object"]
        field_schema["additionalProperties"] = True


for _gendwh_schema_owner in tuple(globals().values()):
    _gendwh_schema = getattr(_gendwh_schema_owner, "schema", None)
    if isinstance(_gendwh_schema, dict):
        _gendwh_relax_adf_nodes(_gendwh_schema)
        _gendwh_allow_issue_field_objects(_gendwh_schema, ("security",))
"""
    if "_gendwh_relax_adf_nodes" not in patched:
        patched = f"{patched.rstrip()}\n\n{relax_adf_patch}\n"

    if patched == original:
        raise RuntimeError(f"Unable to patch tap-jira streams runtime at {streams_path}")

    if "_gendwh_jira_runtime_patch" not in patched:
        patched = patched.replace(
            '"""Stream type classes for tap-jira."""',
            '"""Stream type classes for tap-jira."""\n\n# _gendwh_jira_runtime_patch',
        )
    streams_path.write_text(patched, encoding="utf-8")


async def _ensure_tap_jira_runtime(env: dict[str, str]) -> None:
    install_cmd = ["meltano", "install", "extractor", "tap-jira", "loader", "target-postgres"]
    process = await asyncio.create_subprocess_exec(
        *install_cmd,
        cwd=str(MELTANO_PROJECT_DIR),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError((stderr.decode("utf-8", "replace") or stdout.decode("utf-8", "replace"))[:4000])

    extractor_site_packages = next(
        (MELTANO_PROJECT_DIR / ".meltano" / "extractors" / "tap-jira" / "venv" / "lib").glob("python*/site-packages"),
        None,
    )
    if extractor_site_packages is None:
        raise RuntimeError("tap-jira site-packages directory not found after install")

    _patch_tap_jira_client(extractor_site_packages / "tap_jira" / "client.py")
    _patch_tap_jira_streams(extractor_site_packages / "tap_jira" / "streams.py")


def _extract_records_processed(stdout_text: str, stderr_text: str) -> int:
    value = 0
    combined = f"{stdout_text}\n{stderr_text}"

    for line in combined.splitlines():
        payload: dict | None = None
        try:
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                payload = decoded
        except json.JSONDecodeError:
            payload = None

        if payload:
            for key in ("records_processed", "records", "records_synced", "row_count"):
                raw = payload.get(key)
                if isinstance(raw, int):
                    value = max(value, raw)
            metrics = payload.get("metrics")
            if isinstance(metrics, dict):
                for key in ("records_processed", "records", "records_synced", "row_count"):
                    raw = metrics.get(key)
                    if isinstance(raw, int):
                        value = max(value, raw)

    if value:
        return value

    for pattern in _RECORD_PATTERNS:
        matches = [int(match) for match in pattern.findall(combined)]
        if matches:
            value = max(value, max(matches))

    if value:
        return value

    # Fallback for verbose Singer logs where each record is emitted.
    return len(re.findall(r'"type"\s*:\s*"RECORD"', combined))


def _extract_records_from_payload(payload: dict) -> int:
    value = 0
    for key in ("records_processed", "records", "records_synced", "row_count"):
        raw = payload.get(key)
        if isinstance(raw, int):
            value = max(value, raw)
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        for key in ("records_processed", "records", "records_synced", "row_count"):
            raw = metrics.get(key)
            if isinstance(raw, int):
                value = max(value, raw)
    return value


def _extract_records_from_line(line: str) -> int:
    payload: dict | None = None
    try:
        decoded = json.loads(line)
        if isinstance(decoded, dict):
            payload = decoded
    except json.JSONDecodeError:
        payload = None

    if payload:
        value = _extract_records_from_payload(payload)
        if value > 0:
            return value

    for pattern in _RECORD_PATTERNS:
        match = pattern.search(line)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                continue
    return 0


def _register_meltano_failure() -> None:
    global _meltano_failure_count, _meltano_circuit_open_until
    _meltano_failure_count += 1
    if _meltano_failure_count >= settings.external_service_failure_threshold:
        _meltano_circuit_open_until = time.monotonic() + settings.external_service_cooldown_seconds


def _reset_meltano_circuit() -> None:
    global _meltano_failure_count, _meltano_circuit_open_until
    _meltano_failure_count = 0
    _meltano_circuit_open_until = 0.0


def generate_tap_jira_config(
    source_config: dict,
    extraction_config: dict | None = None,
    streams: list[str] | None = None,
) -> dict:
    extraction = extraction_config or {}
    selected_streams = streams or extraction.get("streams") or ["issues"]
    query_mode = str(extraction.get("query_mode") or "").strip().lower()
    project_keys = extraction.get("project_keys", [])
    raw_jql = extraction.get("jql")
    if query_mode == "jql":
        project_keys = []
    else:
        raw_jql = None
    raw_auth_type = str(extraction.get("auth_type") or "").strip().lower()
    if raw_auth_type == "pat_bearer":
        auth_type = "pat_bearer"
    elif raw_auth_type == "basic_password":
        auth_type = "basic_password"
    else:
        auth_type = "basic_token"
    if auth_type == "pat_bearer":
        raise ValueError(
            "Jira Bearer PAT auth is supported for connection test and preview, but not yet supported for Meltano runs."
        )
    return {
        "domain": _normalize_jira_domain(str(source_config.get("host") or "")),
        "username": source_config.get("username", ""),
        "secret": source_config.get("password", ""),
        "auth_type": auth_type,
        "projects": project_keys,
        "start_date": extraction.get("start_date"),
        "page_size_issues": extraction.get("batch_size", 100),
        "issues_jql": _build_jira_issues_jql(project_keys, raw_jql),
        "streams": selected_streams,
        "incremental_enabled": extraction.get("incremental_enabled", False),
        "replication_key": extraction.get("replication_key", "updated"),
    }


def generate_meltano_config_for_jira_flow(
    source_config: dict,
    target_config: dict,
    state_id: str,
    extraction_config: dict | None = None,
    tables: list[dict] | None = None,
) -> dict:
    selected_streams = []
    for table in tables or []:
        name = str(table.get("table") or table.get("stream") or "").strip()
        if name:
            selected_streams.append(name)
    jira_config = generate_tap_jira_config(
        source_config=source_config,
        extraction_config=extraction_config,
        streams=selected_streams or None,
    )
    return {
        "source_type": "jira",
        "source_config": jira_config,
        "target_config": target_config,
        "state_id": state_id,
    }


async def run_meltano_elt(
    source_config: dict,
    target_config: dict,
    state_id: str,
    tables: list[dict] | None = None,
    source_type: str = "postgres",
    progress_callback: Callable[[int, int | None], Awaitable[None]] | None = None,
) -> MeltanoRunResult:
    """Execute a Meltano ELT run."""
    if time.monotonic() < _meltano_circuit_open_until:
        return MeltanoRunResult(
            success=False,
            error_message="Meltano circuit breaker is open. Retry later.",
        )
    if not MELTANO_PROJECT_DIR.exists():
        _register_meltano_failure()
        return MeltanoRunResult(
            success=False,
            error_message=f"Meltano project directory not found: {MELTANO_PROJECT_DIR}",
        )

    defaults = _target_defaults_from_settings()
    env = {
        **os.environ,
        **_meltano_tls_env(),
        "TARGET_POSTGRES_HOST": target_config.get("host", defaults["host"]),
        "TARGET_POSTGRES_PORT": str(target_config.get("port", defaults["port"])),
        "TARGET_POSTGRES_USER": target_config.get("user", defaults["user"]),
        "TARGET_POSTGRES_PASSWORD": target_config.get("password", defaults["password"]),
        "TARGET_POSTGRES_DATABASE": target_config.get("database", defaults["database"]),
        "TARGET_POSTGRES_SCHEMA": target_config.get("schema", "public"),
    }
    source_type_normalized = (source_type or "postgres").lower()
    if source_type_normalized == "s3":
        env["TAP_S3_CSV_AWS_ACCESS_KEY_ID"] = source_config["aws_access_key_id"]
        env["TAP_S3_CSV_AWS_SECRET_ACCESS_KEY"] = source_config["aws_secret_access_key"]
        env["TAP_S3_CSV_BUCKET"] = source_config["bucket"]
        endpoint_url = str(source_config.get("aws_endpoint_url") or "").strip()
        if endpoint_url:
            env["TAP_S3_CSV_AWS_ENDPOINT_URL"] = endpoint_url
        if tables:
            env["TAP_S3_CSV_TABLES"] = json.dumps(tables, ensure_ascii=False)
        cmd = [
            "meltano",
            "run",
            "--force",
            "--state-id-suffix",
            state_id,
            "tap-s3-csv",
            "target-postgres",
        ]
    elif source_type_normalized == "jira":
        jira_config = generate_tap_jira_config(
            source_config=source_config,
            extraction_config=source_config.get("extraction_config"),
            streams=[
                str(item.get("table") or item.get("stream") or "").strip()
                for item in (tables or [])
                if str(item.get("table") or item.get("stream") or "").strip()
            ]
            or None,
        )
        env["TAP_JIRA_DOMAIN"] = str(jira_config.get("domain") or "")
        # tap-jira exposes email/api_token in Meltano config, but your on-prem Jira accepts
        # username/password via the same Basic auth header, so we map both basic modes here.
        env["TAP_JIRA_EMAIL"] = str(jira_config.get("username") or "")
        env["TAP_JIRA_API_TOKEN"] = str(jira_config.get("secret") or "")
        if jira_config.get("start_date"):
            env["TAP_JIRA_START_DATE"] = str(jira_config.get("start_date"))
        if jira_config.get("page_size_issues"):
            env["TAP_JIRA_PAGE_SIZE_ISSUES"] = str(jira_config.get("page_size_issues"))
        if jira_config.get("issues_jql"):
            env["TAP_JIRA_STREAM_OPTIONS_ISSUES_JQL"] = str(jira_config.get("issues_jql"))
        env["TAP_JIRA_API_VERSION"] = _detect_jira_api_version(
            str(source_config.get("host") or ""),
            str(jira_config.get("auth_type") or ""),
        )
        if env.get("REQUESTS_CA_BUNDLE"):
            env["TAP_JIRA_CA_BUNDLE"] = env["REQUESTS_CA_BUNDLE"]

        metadata: dict[str, dict] = {}
        select_rules: list[str] = []
        for table in tables or []:
            stream_name = str(table.get("table") or table.get("stream") or "").strip()
            if not stream_name:
                continue
            replication_method = str(table.get("replication_method", "FULL_TABLE")).upper()
            replication_key = table.get("replication_key")
            stream_metadata: dict[str, object] = {
                "selected": True,
                "replication-method": replication_method,
            }
            if replication_method == "INCREMENTAL" and replication_key:
                stream_metadata["replication-key"] = replication_key
                stream_metadata[str(replication_key)] = {"is-replication-key": True}
            metadata[stream_name] = stream_metadata
            select_rules.append(f"{stream_name}.*")
        if metadata:
            env["TAP_JIRA__METADATA"] = json.dumps(metadata, ensure_ascii=False)
        if select_rules:
            env["TAP_JIRA__SELECT"] = json.dumps(sorted(set(select_rules)), ensure_ascii=False)

        await _ensure_tap_jira_runtime(env)
        cmd = [
            "meltano",
            "run",
            "--force",
            "--state-id-suffix",
            state_id,
            "tap-jira",
            "target-postgres",
        ]
    else:
        env["TAP_POSTGRES_HOST"] = source_config["host"]
        env["TAP_POSTGRES_PORT"] = str(source_config["port"])
        env["TAP_POSTGRES_USER"] = source_config["username"]
        env["TAP_POSTGRES_PASSWORD"] = source_config["password"]
        env["TAP_POSTGRES_DATABASE"] = source_config["database"]

        if tables:
            env["TAP_POSTGRES_FLOW_TABLES"] = json.dumps(tables, ensure_ascii=False)
            metadata: dict[str, dict] = {}
            select_rules: list[str] = []
            stream_replication = {
                f'{table["schema"]}.{table["table"]}': table["replication_key"]
                for table in tables
                if table.get("replication_method") == "INCREMENTAL" and table.get("replication_key")
            }
            for table in tables:
                schema = str(table.get("schema", "")).strip()
                name = str(table.get("table", "")).strip()
                if not schema or not name:
                    continue

                replication_method = str(table.get("replication_method", "FULL_TABLE")).upper()
                replication_key = table.get("replication_key")
                stream_metadata: dict[str, object] = {
                    "selected": True,
                    "replication-method": replication_method,
                }
                if replication_method == "INCREMENTAL" and replication_key:
                    stream_metadata["replication-key"] = replication_key
                    stream_metadata[str(replication_key)] = {"is-replication-key": True}

                stream_ids = [f"{schema}-{name}", f"{schema}.{name}"]
                for stream_id in stream_ids:
                    metadata[stream_id] = stream_metadata
                    select_rules.append(f"{stream_id}.*")

            if stream_replication:
                env["TAP_POSTGRES_REPLICATION_KEYS"] = json.dumps(stream_replication, ensure_ascii=False)
            if metadata:
                env["TAP_POSTGRES__METADATA"] = json.dumps(metadata, ensure_ascii=False)
            if select_rules:
                env["TAP_POSTGRES__SELECT"] = json.dumps(sorted(set(select_rules)), ensure_ascii=False)

        cmd = [
            "meltano",
            "run",
            "--force",
            "--state-id-suffix",
            state_id,
            "tap-postgres",
            "target-postgres",
        ]

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(MELTANO_PROJECT_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_tail: deque[str] = deque(maxlen=800)
        stderr_tail: deque[str] = deque(maxlen=800)
        records_processed = 0

        async def _consume_stream(stream, buffer: deque[str]) -> None:
            nonlocal records_processed
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip("\n")
                buffer.append(decoded)

                # Singer RECORD lines may not include counters.
                if re.search(r'"type"\s*:\s*"RECORD"', decoded):
                    records_processed += 1
                    if progress_callback:
                        await progress_callback(records_processed, None)
                    continue

                parsed_value = _extract_records_from_line(decoded)
                if parsed_value > records_processed:
                    records_processed = parsed_value
                    if progress_callback:
                        await progress_callback(records_processed, None)

        await asyncio.wait_for(
            asyncio.gather(
                _consume_stream(process.stdout, stdout_tail),
                _consume_stream(process.stderr, stderr_tail),
            ),
            timeout=settings.meltano_command_timeout_seconds,
        )
        await asyncio.wait_for(process.wait(), timeout=5)

        stdout_text = "\n".join(stdout_tail)
        stderr_text = "\n".join(stderr_tail)
        fallback_records = _extract_records_processed(stdout_text, stderr_text)
        records_processed = max(records_processed, fallback_records)
        tables_processed = len(tables or [])

        if process.returncode == 0:
            _reset_meltano_circuit()
            if progress_callback:
                await progress_callback(records_processed, None)
            return MeltanoRunResult(
                success=True,
                records_processed=records_processed,
                tables_processed=tables_processed,
                state_file=str(MELTANO_PROJECT_DIR / ".meltano" / "run" / f"{state_id}.json"),
            )
        else:
            _register_meltano_failure()
            return MeltanoRunResult(
                success=False,
                records_processed=records_processed,
                tables_processed=tables_processed,
                error_message=(stderr_text or stdout_text)[:2000],
            )
    except TimeoutError:
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        _register_meltano_failure()
        return MeltanoRunResult(
            success=False,
            error_message=f"Meltano command timed out after {settings.meltano_command_timeout_seconds} seconds",
        )
    except FileNotFoundError as exc:
        _register_meltano_failure()
        return MeltanoRunResult(
            success=False,
            error_message=f"Meltano binary or project path not found: {exc}",
        )
    except Exception as e:
        _register_meltano_failure()
        return MeltanoRunResult(success=False, error_message=str(e))


async def run_preview(
    source_config: dict,
    extraction_config: dict | None = None,
    streams: list[str] | None = None,
    row_limit: int = 100,
) -> MeltanoRunResult:
    extraction = extraction_config or {}
    preview_tables = [{"table": stream} for stream in (streams or extraction.get("streams") or ["issues"])]
    target_config = {"schema": "jira_preview"}
    state_id = f"jira_preview_{int(time.time())}"
    preview_source = {
        **source_config,
        "extraction_config": {
            **extraction,
            "batch_size": min(max(row_limit, 1), 100),
        },
    }
    return await run_meltano_elt(
        source_config=preview_source,
        target_config=target_config,
        state_id=state_id,
        tables=preview_tables,
        source_type="jira",
    )
