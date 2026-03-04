from pydantic import ValidationError

from src.core.config import Settings


def test_settings_rejects_short_encryption_key() -> None:
    try:
        Settings(db_encryption_key="short")
        assert False, "Expected validation error for short DB_ENCRYPTION_KEY"
    except ValidationError:
        assert True


def test_settings_accepts_secure_values_when_enforced() -> None:
    settings = Settings(
        app_secret_key="secure-app-secret-value",
        db_encryption_key="secure-encryption-key-value-123",
        database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
        database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
        redis_url="redis://:strong-redis-pass@localhost:6379/0",
        enforce_secure_secrets=True,
    )
    assert settings.enforce_secure_secrets is True


def test_settings_rejects_redis_without_password_when_enforced() -> None:
    try:
        Settings(
            app_secret_key="secure-app-secret-value",
            db_encryption_key="secure-encryption-key-value-123",
            database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
            database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
            redis_url="redis://localhost:6379/0",
            enforce_secure_secrets=True,
        )
        assert False, "Expected validation error for insecure REDIS_URL"
    except ValidationError:
        assert True
