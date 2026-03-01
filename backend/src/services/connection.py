"""Connection testing and credential encryption service (T038, T039)."""

import time
from dataclasses import dataclass

import asyncpg
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
