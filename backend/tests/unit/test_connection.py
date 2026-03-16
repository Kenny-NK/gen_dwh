from unittest.mock import AsyncMock

import pytest

from src.services.connection import discover_schemas


@pytest.mark.asyncio
async def test_discover_schemas_prioritizes_schemas_with_tables(monkeypatch):
    conn = AsyncMock()
    conn.fetch.return_value = [
        {"schema_name": "sh2"},
        {"schema_name": "public"},
    ]
    conn.close = AsyncMock()

    connect = AsyncMock(return_value=conn)
    monkeypatch.setattr("src.services.connection.asyncpg.connect", connect)

    schemas = await discover_schemas("db.example.local", 5432, "analytics", "reader", "secret")

    assert schemas == ["sh2", "public"]
    fetch_sql = conn.fetch.await_args.args[0]
    assert "FROM information_schema.schemata s" in fetch_sql
    assert "LEFT JOIN information_schema.tables t" in fetch_sql
    assert "t.table_type = 'BASE TABLE'" in fetch_sql
    assert "ORDER BY COUNT(t.table_name) DESC" in fetch_sql
    conn.close.assert_awaited_once()
