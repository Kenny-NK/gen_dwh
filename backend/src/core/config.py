"""Application configuration module (T015)."""

from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "GenDWH"
    app_secret_key: str = "dev-only-change-in-env-please"
    debug: bool = False
    rate_limit_per_minute: int = Field(default=600, ge=0, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    jwks_cache_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)
    http_client_timeout_seconds: float = Field(default=5.0, gt=0.1, le=60.0)
    external_ca_bundle_path: str = ""
    jira_client_cert_path: str = ""
    jira_client_key_path: str = ""
    jira_client_cert_password: str = ""
    jira_client_cert_password_file: str = ""
    vault_addr: str = ""
    vault_auth_method: str = "token"
    vault_token: str = ""
    vault_token_file: str = ""
    vault_approle_mount: str = "approle"
    vault_role_id: str = ""
    vault_role_id_file: str = ""
    vault_secret_id: str = ""
    vault_secret_id_file: str = ""
    vault_kv_mount: str = "secret"
    vault_kv_version: str = "v2"
    vault_jira_client_cert_secret_path: str = ""
    vault_jira_client_cert_field: str = "p12_base64"
    vault_jira_client_cert_password_field: str = "password"
    vault_jira_client_cert_filename_field: str = "filename"
    vault_jira_client_cert_pem_field: str = "cert_pem"
    vault_jira_client_key_field: str = "key_pem"
    external_service_failure_threshold: int = Field(default=5, ge=1, le=20)
    external_service_cooldown_seconds: int = Field(default=60, ge=5, le=3_600)
    meltano_command_timeout_seconds: int = Field(default=3600, ge=60, le=86_400)
    stale_pending_run_minutes: int = Field(default=15, ge=1, le=1_440)
    orphan_pending_run_grace_seconds: int = Field(default=90, ge=5, le=3_600)
    jira_connector_enabled: bool = True
    trust_proxy_headers: bool = False
    allow_realm_tenant_fallback: bool = False
    cors_allowed_origins: str = "http://localhost:5173"
    enforce_secure_secrets: bool = True
    auth_cookie_name: str = "gendwh_access_token"
    auth_cookie_max_age_seconds: int = Field(default=3600, ge=300, le=86_400)
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    preview_default_mode: str = "auto"
    preview_allow_mode_override: bool = True
    preview_live_ttl_minutes: int = Field(default=30, ge=1, le=1_440)
    preview_snapshot_ttl_minutes: int = Field(default=120, ge=1, le=4_320)

    # Database
    database_system_url: str = "postgresql+asyncpg://gendwh:gendwh_local_dev_pw@localhost:5432/gendwh_system"
    database_business_url: str = "postgresql+asyncpg://gendwh:gendwh_local_dev_pw@localhost:5433/gendwh_business"
    db_encryption_key: str = "dev-only-db-encryption-key-change-me"

    # Redis
    redis_url: str = "redis://:gendwh_local_dev_redis_pw@localhost:6379/0"

    # Keycloak
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "gendwh"
    keycloak_client_id: str = "gendwh-app"
    keycloak_client_secret: str = ""
    keycloak_issuer: str | None = None
    bootstrap_tenant_subdomain: str = "acme"
    bootstrap_tenant_name: str = "Acme Corp"
    bootstrap_tenant_schema: str = "tenant_acme"

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_value(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if not self.jira_client_cert_password and self.jira_client_cert_password_file:
            secret_path = Path(self.jira_client_cert_password_file)
            if not secret_path.is_file():
                raise ValueError("JIRA_CLIENT_CERT_PASSWORD_FILE must point to an existing file")
            password = secret_path.read_text(encoding="utf-8").strip()
            if not password:
                raise ValueError("JIRA_CLIENT_CERT_PASSWORD_FILE must not be empty")
            self.jira_client_cert_password = password

        if not self.vault_token and self.vault_token_file:
            token_path = Path(self.vault_token_file)
            if not token_path.is_file():
                raise ValueError("VAULT_TOKEN_FILE must point to an existing file")
            token = token_path.read_text(encoding="utf-8").strip()
            if not token:
                raise ValueError("VAULT_TOKEN_FILE must not be empty")
            self.vault_token = token

        if not self.vault_role_id and self.vault_role_id_file:
            role_id_path = Path(self.vault_role_id_file)
            if not role_id_path.is_file():
                raise ValueError("VAULT_ROLE_ID_FILE must point to an existing file")
            role_id = role_id_path.read_text(encoding="utf-8").strip()
            if not role_id:
                raise ValueError("VAULT_ROLE_ID_FILE must not be empty")
            self.vault_role_id = role_id

        if not self.vault_secret_id and self.vault_secret_id_file:
            secret_id_path = Path(self.vault_secret_id_file)
            if not secret_id_path.is_file():
                raise ValueError("VAULT_SECRET_ID_FILE must point to an existing file")
            secret_id = secret_id_path.read_text(encoding="utf-8").strip()
            if not secret_id:
                raise ValueError("VAULT_SECRET_ID_FILE must not be empty")
            self.vault_secret_id = secret_id

        if len(self.db_encryption_key) < 16:
            raise ValueError("DB_ENCRYPTION_KEY must be at least 16 characters long")

        if not self.debug and self.enforce_secure_secrets:
            weak_values = {
                "",
                "change-me",
                "change_me",
                "change-me-32-byte-hex-key",
                "change_me_32_byte_hex_key_here_00",
                "change_me_app_secret",
                "dev-only-change-in-env-please",
                "dev-only-db-encryption-key-change-me",
            }
            if self.app_secret_key in weak_values:
                raise ValueError("APP_SECRET_KEY must be changed from default value")
            if self.db_encryption_key in weak_values:
                raise ValueError("DB_ENCRYPTION_KEY must be changed from default value")
            if "password@localhost" in self.database_system_url:
                raise ValueError("DATABASE_SYSTEM_URL must not use default password")
            if "password@localhost" in self.database_business_url:
                raise ValueError("DATABASE_BUSINESS_URL must not use default password")
            parsed_redis = urlparse(self.redis_url)
            if parsed_redis.scheme.startswith("redis") and not parsed_redis.password:
                raise ValueError("REDIS_URL must include password when ENFORCE_SECURE_SECRETS=true")

        if self.auth_cookie_samesite.lower() not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE must be one of: lax, strict, none")

        if self.preview_default_mode.lower() not in {"auto", "live", "snapshot"}:
            raise ValueError("PREVIEW_DEFAULT_MODE must be one of: auto, live, snapshot")

        if self.vault_kv_version.lower() not in {"v1", "v2"}:
            raise ValueError("VAULT_KV_VERSION must be one of: v1, v2")

        if self.vault_auth_method.lower() not in {"token", "approle"}:
            raise ValueError("VAULT_AUTH_METHOD must be one of: token, approle")

        return self

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
