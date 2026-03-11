"""Secret manager helpers for external integrations."""

from __future__ import annotations

from functools import lru_cache

import httpx

from src.core.config import settings


def _vault_verify() -> bool | str:
    ca_bundle_path = str(settings.external_ca_bundle_path or "").strip()
    if ca_bundle_path:
        return ca_bundle_path
    return True


def _vault_addr() -> str:
    addr = str(settings.vault_addr or "").strip().rstrip("/")
    if not addr:
        raise ValueError("Vault address is not configured")
    return addr


def _vault_headers() -> dict[str, str]:
    token = get_vault_client_token()
    return {"X-Vault-Token": token}


def _vault_secret_url(path: str) -> str:
    mount = str(settings.vault_kv_mount or "secret").strip().strip("/")
    normalized_path = str(path or "").strip().strip("/")
    if not normalized_path:
        raise ValueError("Vault secret path must not be empty")

    if settings.vault_kv_version.lower() == "v2":
        return f"{_vault_addr()}/v1/{mount}/data/{normalized_path}"
    return f"{_vault_addr()}/v1/{mount}/{normalized_path}"


@lru_cache(maxsize=1)
def get_vault_client_token() -> str:
    auth_method = str(settings.vault_auth_method or "token").strip().lower()
    if auth_method == "token":
        token = str(settings.vault_token or "").strip()
        if not token:
            raise ValueError("Vault token is not configured")
        return token

    role_id = str(settings.vault_role_id or "").strip()
    secret_id = str(settings.vault_secret_id or "").strip()
    if not role_id or not secret_id:
        raise ValueError("Vault AppRole credentials are not configured")

    approle_mount = str(settings.vault_approle_mount or "approle").strip().strip("/")
    login_url = f"{_vault_addr()}/v1/auth/{approle_mount}/login"
    with httpx.Client(timeout=settings.http_client_timeout_seconds, verify=_vault_verify()) as client:
        response = client.post(
            login_url,
            json={
                "role_id": role_id,
                "secret_id": secret_id,
            },
        )
        response.raise_for_status()
        payload = response.json()

    auth_payload = payload.get("auth")
    if not isinstance(auth_payload, dict):
        raise ValueError("Unexpected Vault AppRole login response")

    token = str(auth_payload.get("client_token") or "").strip()
    if not token:
        raise ValueError("Vault AppRole login did not return client token")
    return token


@lru_cache(maxsize=8)
def get_vault_secret(path: str) -> dict[str, object]:
    url = _vault_secret_url(path)
    with httpx.Client(
        timeout=settings.http_client_timeout_seconds,
        verify=_vault_verify(),
        headers=_vault_headers(),
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected Vault response for secret path: {path}")

    if settings.vault_kv_version.lower() == "v2":
        nested = data.get("data")
        if not isinstance(nested, dict):
            raise ValueError(f"Unexpected Vault KV v2 response for secret path: {path}")
        return nested
    return data


def clear_vault_secret_cache() -> None:
    get_vault_secret.cache_clear()
    get_vault_client_token.cache_clear()
