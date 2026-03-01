"""Meltano orchestration service (T075)."""

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from src.core.config import settings


@dataclass
class MeltanoRunResult:
    success: bool
    records_processed: int = 0
    tables_processed: int = 0
    error_message: str | None = None
    state_file: str | None = None


MELTANO_PROJECT_DIR = Path(__file__).parent.parent.parent.parent / "meltano"
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


def _register_meltano_failure() -> None:
    global _meltano_failure_count, _meltano_circuit_open_until
    _meltano_failure_count += 1
    if _meltano_failure_count >= settings.external_service_failure_threshold:
        _meltano_circuit_open_until = time.monotonic() + settings.external_service_cooldown_seconds


def _reset_meltano_circuit() -> None:
    global _meltano_failure_count, _meltano_circuit_open_until
    _meltano_failure_count = 0
    _meltano_circuit_open_until = 0.0


async def run_meltano_elt(
    source_config: dict,
    target_config: dict,
    state_id: str,
    tables: list[dict] | None = None,
) -> MeltanoRunResult:
    """Execute a Meltano ELT run."""
    if time.monotonic() < _meltano_circuit_open_until:
        return MeltanoRunResult(
            success=False,
            error_message="Meltano circuit breaker is open. Retry later.",
        )

    defaults = _target_defaults_from_settings()
    env = {
        **os.environ,
        "TAP_POSTGRES_HOST": source_config["host"],
        "TAP_POSTGRES_PORT": str(source_config["port"]),
        "TAP_POSTGRES_USER": source_config["username"],
        "TAP_POSTGRES_PASSWORD": source_config["password"],
        "TAP_POSTGRES_DATABASE": source_config["database"],
        "TARGET_POSTGRES_HOST": target_config.get("host", defaults["host"]),
        "TARGET_POSTGRES_PORT": str(target_config.get("port", defaults["port"])),
        "TARGET_POSTGRES_USER": target_config.get("user", defaults["user"]),
        "TARGET_POSTGRES_PASSWORD": target_config.get("password", defaults["password"]),
        "TARGET_POSTGRES_DATABASE": target_config.get("database", defaults["database"]),
        "TARGET_POSTGRES_SCHEMA": target_config.get("schema", "public"),
    }
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
        "meltano", "run",
        "--state-id", state_id,
        "tap-postgres", "target-postgres",
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(MELTANO_PROJECT_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=settings.meltano_command_timeout_seconds,
        )
        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        records_processed = _extract_records_processed(stdout_text, stderr_text)
        tables_processed = len(tables or [])

        if process.returncode == 0:
            _reset_meltano_circuit()
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
        _register_meltano_failure()
        return MeltanoRunResult(
            success=False,
            error_message=f"Meltano command timed out after {settings.meltano_command_timeout_seconds} seconds",
        )
    except FileNotFoundError:
        _register_meltano_failure()
        return MeltanoRunResult(
            success=False,
            error_message="Meltano CLI not found. Ensure Meltano is installed.",
        )
    except Exception as e:
        _register_meltano_failure()
        return MeltanoRunResult(success=False, error_message=str(e))
