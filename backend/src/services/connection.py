"""Connection testing and credential encryption service (T038, T039)."""

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import asyncpg
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings


@dataclass
class ConnectionTestResult:
    success: bool
    message: str
    server_version: str | None = None
    latency_ms: float | None = None
    error_code: str | None = None


def build_s3_endpoint_url(host: str, port: int) -> str:
    """Build endpoint URL for S3-compatible services."""
    value = (host or "").strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if parsed.port is not None:
            return value.rstrip("/")
        default_port = 443 if parsed.scheme == "https" else 80
        if port in (0, default_port):
            return value.rstrip("/")
        hostname = parsed.hostname or parsed.netloc
        if not hostname:
            return value.rstrip("/")
        return urlunparse(parsed._replace(netloc=f"{hostname}:{port}")).rstrip("/")
    if not value:
        return "https://s3.amazonaws.com"
    if port in (80, 443):
        scheme = "http" if port == 80 else "https"
        return f"{scheme}://{value}"
    return f"http://{value}:{port}"


async def test_connection(
    host: str, port: int, database: str, username: str, password: str
) -> ConnectionTestResult:
    """Test a PostgreSQL connection and return result."""
    start = time.monotonic()
    try:
        conn = await asyncpg.connect(
            host=host, port=port, database=database, user=username, password=password, timeout=10
        )
        try:
            version = await conn.fetchval("SELECT version()")
            latency = (time.monotonic() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message="Подключение успешно",
                server_version=version,
                latency_ms=round(latency, 2),
            )
        finally:
            await conn.close()
    except asyncpg.InvalidPasswordError:
        return ConnectionTestResult(
            success=False, message="Неверные учетные данные", error_code="auth_failed"
        )
    except asyncpg.InvalidCatalogNameError:
        return ConnectionTestResult(
            success=False,
            message=f"База данных '{database}' не найдена",
            error_code="database_not_found",
        )
    except OSError:
        return ConnectionTestResult(
            success=False, message="Не удалось установить соединение", error_code="connection_refused"
        )
    except TimeoutError:
        return ConnectionTestResult(
            success=False, message="Тайм-аут подключения", error_code="timeout"
        )
    except Exception as e:
        return ConnectionTestResult(
            success=False, message=str(e), error_code="unknown"
        )


async def test_s3_connection(
    host: str,
    port: int,
    bucket: str,
    access_key_id: str,
    secret_access_key: str,
) -> ConnectionTestResult:
    """Validate S3 credentials and bucket availability."""

    endpoint_url = build_s3_endpoint_url(host, port)
    start = time.monotonic()

    def _test_sync() -> None:
        client = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
        )
        client.list_objects_v2(Bucket=bucket, MaxKeys=1)

    try:
        await asyncio.to_thread(_test_sync)
        latency = (time.monotonic() - start) * 1000
        return ConnectionTestResult(
            success=True,
            message="Подключение к S3 успешно",
            server_version=endpoint_url,
            latency_ms=round(latency, 2),
        )
    except ClientError as exc:
        error_code = str(exc.response.get("Error", {}).get("Code", "s3_error"))
        message = str(exc.response.get("Error", {}).get("Message", exc))
        return ConnectionTestResult(
            success=False,
            message=f"S3 ошибка: {message}",
            error_code=error_code,
        )
    except (BotoCoreError, OSError, TimeoutError) as exc:
        return ConnectionTestResult(
            success=False,
            message=f"Не удалось подключиться к S3: {exc}",
            error_code="s3_connection_error",
        )
    except Exception as exc:
        return ConnectionTestResult(
            success=False,
            message=f"S3 неизвестная ошибка: {exc}",
            error_code="s3_unknown",
        )


async def encrypt_password(session: AsyncSession, password: str) -> bytes:
    """Encrypt password using pgcrypto."""
    result = await session.execute(
        text("SELECT pgp_sym_encrypt(:password, :key)"),
        {"password": password, "key": settings.db_encryption_key},
    )
    return result.scalar()


async def decrypt_password(session: AsyncSession, encrypted: bytes) -> str:
    """Decrypt password using pgcrypto."""
    result = await session.execute(
        text("SELECT pgp_sym_decrypt(:encrypted, :key)"),
        {"encrypted": encrypted, "key": settings.db_encryption_key},
    )
    return result.scalar()


async def discover_schemas(
    host: str, port: int, database: str, username: str, password: str
) -> list[str]:
    """Discover available schemas in the source database."""
    conn = await asyncpg.connect(
        host=host, port=port, database=database, user=username, password=password, timeout=10
    )
    try:
        rows = await conn.fetch(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast') "
            "ORDER BY schema_name"
        )
        return [row["schema_name"] for row in rows]
    finally:
        await conn.close()


async def discover_tables(
    host: str, port: int, database: str, username: str, password: str, schema: str
) -> list[dict]:
    """Discover tables and columns in a schema."""
    conn = await asyncpg.connect(
        host=host, port=port, database=database, user=username, password=password, timeout=10
    )
    try:
        # Get tables with row counts
        tables = await conn.fetch(
            "SELECT t.table_name, "
            "  COALESCE(( "
            "    SELECT c.reltuples::bigint "
            "    FROM pg_class c "
            "    JOIN pg_namespace n ON n.oid = c.relnamespace "
            "    WHERE c.relkind = 'r' AND n.nspname = t.table_schema AND c.relname = t.table_name "
            "  ), 0) as row_count "
            "FROM information_schema.tables t "
            "WHERE t.table_schema = $1 AND t.table_type = 'BASE TABLE' "
            "ORDER BY t.table_name",
            schema,
        )

        result = []
        for table in tables:
            cols = await conn.fetch(
                "SELECT c.column_name, c.data_type, c.is_nullable, "
                "  CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key "
                "FROM information_schema.columns c "
                "LEFT JOIN ("
                "  SELECT ku.column_name "
                "  FROM information_schema.table_constraints tc "
                "  JOIN information_schema.key_column_usage ku "
                "    ON tc.constraint_name = ku.constraint_name "
                "  WHERE tc.table_schema = $1 AND tc.table_name = $2 "
                "    AND tc.constraint_type = 'PRIMARY KEY'"
                ") pk ON pk.column_name = c.column_name "
                "WHERE c.table_schema = $1 AND c.table_name = $2 "
                "ORDER BY c.ordinal_position",
                schema,
                table["table_name"],
            )
            result.append({
                "name": table["table_name"],
                "row_count": max(0, table["row_count"] or 0),
                "columns": [
                    {
                        "name": col["column_name"],
                        "data_type": col["data_type"],
                        "is_nullable": col["is_nullable"] == "YES",
                        "is_primary_key": col["is_primary_key"],
                    }
                    for col in cols
                ],
            })
        return result
    finally:
        await conn.close()


async def estimate_tables_row_count(
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    tables: list[tuple[str, str]],
) -> int:
    """Estimate total rows for selected PostgreSQL tables using pg_class.reltuples."""
    if not tables:
        return 0

    conn = await asyncpg.connect(
        host=host, port=port, database=database, user=username, password=password, timeout=10
    )
    try:
        total = 0
        for schema_name, table_name in tables:
            row_count = await conn.fetchval(
                """
                SELECT COALESCE((
                    SELECT GREATEST(c.reltuples::bigint, 0)
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'r'
                      AND n.nspname = $1
                      AND c.relname = $2
                ), 0)
                """,
                schema_name,
                table_name,
            )
            total += int(row_count or 0)
        return total
    finally:
        await conn.close()


async def discover_s3_objects(
    host: str,
    port: int,
    bucket: str,
    access_key_id: str,
    secret_access_key: str,
    prefix: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Discover CSV/XLSX objects in S3 bucket and return table-like metadata."""

    endpoint_url = build_s3_endpoint_url(host, port)

    def _discover_sync() -> list[dict]:
        client = boto3.client(
            "s3",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
        )
        kwargs: dict[str, object] = {"Bucket": bucket, "MaxKeys": limit}
        if prefix:
            kwargs["Prefix"] = prefix
        response = client.list_objects_v2(**kwargs)
        objects = response.get("Contents", []) or []
        result: list[dict] = []
        for item in objects:
            key = str(item.get("Key") or "")
            if not key:
                continue
            lower_key = key.lower()
            if not (lower_key.endswith(".csv") or lower_key.endswith(".xlsx")):
                continue
            result.append(
                {
                    "name": key,
                    "row_count": 0,
                    "columns": [],
                    "format": "xlsx" if lower_key.endswith(".xlsx") else "csv",
                }
            )
        return sorted(result, key=lambda obj: obj["name"])

    return await asyncio.to_thread(_discover_sync)
