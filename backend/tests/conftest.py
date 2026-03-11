"""Test configuration and fixtures."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-value-123")
os.environ.setdefault("DB_ENCRYPTION_KEY", "test-db-encryption-key-123")
os.environ.setdefault("REDIS_URL", "redis://:test-redis-pass@localhost:6379/0")

from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
