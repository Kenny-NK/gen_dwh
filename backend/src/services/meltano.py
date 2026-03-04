"""Meltano orchestration service (T075)."""

import asyncio
import json
import os
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

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
            "--state-id-suffix",
            state_id,
            "tap-s3-csv",
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
