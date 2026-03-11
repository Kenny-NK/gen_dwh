from pydantic import ValidationError

from src.core.config import Settings


def test_settings_rejects_short_encryption_key() -> None:
    try:
        Settings(db_encryption_key="short")
        raise AssertionError("Expected validation error for short DB_ENCRYPTION_KEY")
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
        raise AssertionError("Expected validation error for insecure REDIS_URL")
    except ValidationError:
        assert True


def test_settings_accepts_release_debug_alias() -> None:
    settings = Settings(
        debug="release",
        app_secret_key="secure-app-secret-value",
        db_encryption_key="secure-encryption-key-value-123",
        database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
        database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
        redis_url="redis://:strong-redis-pass@localhost:6379/0",
        enforce_secure_secrets=True,
    )
    assert settings.debug is False


def test_settings_rejects_current_dev_defaults_when_enforced() -> None:
    try:
        Settings(
            debug=False,
            app_secret_key="dev-only-change-in-env-please",
            db_encryption_key="dev-only-db-encryption-key-change-me",
            database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
            database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
            redis_url="redis://:strong-redis-pass@localhost:6379/0",
            enforce_secure_secrets=True,
        )
        raise AssertionError("Expected validation error for current dev default secrets")
    except ValidationError:
        assert True


def test_settings_loads_jira_client_cert_password_from_file(tmp_path) -> None:
    secret_file = tmp_path / "jira-client-cert-password"
    secret_file.write_text("super-secret\n", encoding="utf-8")

    settings = Settings(
        jira_client_cert_password="",
        jira_client_cert_password_file=str(secret_file),
        app_secret_key="secure-app-secret-value",
        db_encryption_key="secure-encryption-key-value-123",
        database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
        database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
        redis_url="redis://:strong-redis-pass@localhost:6379/0",
        enforce_secure_secrets=True,
    )

    assert settings.jira_client_cert_password == "super-secret"


def test_settings_rejects_empty_jira_client_cert_password_file(tmp_path) -> None:
    secret_file = tmp_path / "jira-client-cert-password"
    secret_file.write_text("\n", encoding="utf-8")

    try:
        Settings(
            jira_client_cert_password="",
            jira_client_cert_password_file=str(secret_file),
            app_secret_key="secure-app-secret-value",
            db_encryption_key="secure-encryption-key-value-123",
            database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
            database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
            redis_url="redis://:strong-redis-pass@localhost:6379/0",
            enforce_secure_secrets=True,
        )
        raise AssertionError("Expected validation error for empty JIRA_CLIENT_CERT_PASSWORD_FILE")
    except ValidationError:
        assert True


def test_settings_loads_vault_token_from_file(tmp_path) -> None:
    token_file = tmp_path / "vault-token"
    token_file.write_text("vault-token-value\n", encoding="utf-8")

    settings = Settings(
        vault_token="",
        vault_token_file=str(token_file),
        app_secret_key="secure-app-secret-value",
        db_encryption_key="secure-encryption-key-value-123",
        database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
        database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
        redis_url="redis://:strong-redis-pass@localhost:6379/0",
        enforce_secure_secrets=True,
    )

    assert settings.vault_token == "vault-token-value"


def test_settings_rejects_invalid_vault_kv_version() -> None:
    try:
        Settings(
            vault_kv_version="v3",
            app_secret_key="secure-app-secret-value",
            db_encryption_key="secure-encryption-key-value-123",
            database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
            database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
            redis_url="redis://:strong-redis-pass@localhost:6379/0",
            enforce_secure_secrets=True,
        )
        raise AssertionError("Expected validation error for invalid VAULT_KV_VERSION")
    except ValidationError:
        assert True


def test_settings_loads_vault_approle_credentials_from_files(tmp_path) -> None:
    role_id_file = tmp_path / "vault-role-id"
    secret_id_file = tmp_path / "vault-secret-id"
    role_id_file.write_text("role-id-value\n", encoding="utf-8")
    secret_id_file.write_text("secret-id-value\n", encoding="utf-8")

    settings = Settings(
        vault_auth_method="approle",
        vault_role_id="",
        vault_role_id_file=str(role_id_file),
        vault_secret_id="",
        vault_secret_id_file=str(secret_id_file),
        app_secret_key="secure-app-secret-value",
        db_encryption_key="secure-encryption-key-value-123",
        database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
        database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
        redis_url="redis://:strong-redis-pass@localhost:6379/0",
        enforce_secure_secrets=True,
    )

    assert settings.vault_role_id == "role-id-value"
    assert settings.vault_secret_id == "secret-id-value"


def test_settings_rejects_invalid_vault_auth_method() -> None:
    try:
        Settings(
            vault_auth_method="ldap",
            app_secret_key="secure-app-secret-value",
            db_encryption_key="secure-encryption-key-value-123",
            database_system_url="postgresql+asyncpg://u:p@localhost:5432/db1",
            database_business_url="postgresql+asyncpg://u:p@localhost:5433/db2",
            redis_url="redis://:strong-redis-pass@localhost:6379/0",
            enforce_secure_secrets=True,
        )
        raise AssertionError("Expected validation error for invalid VAULT_AUTH_METHOD")
    except ValidationError:
        assert True
