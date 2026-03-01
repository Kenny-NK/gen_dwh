"""Security utilities - JWT validation, password hashing (T016)."""

import asyncio
import time

import httpx
from jose import JWTError, jwt

from src.core.config import settings


_jwks_cache: dict | None = None
_jwks_expires_at: float = 0.0
_jwks_lock = asyncio.Lock()
_keycloak_failure_count = 0
_keycloak_circuit_open_until = 0.0


class KeycloakUnavailableError(RuntimeError):
    """Raised when Keycloak JWKS cannot be fetched."""


async def fetch_jwks() -> dict:
    """Fetch JWKS from Keycloak for JWT verification."""
    global _jwks_cache, _jwks_expires_at, _keycloak_failure_count, _keycloak_circuit_open_until
    now = time.monotonic()
    if _jwks_cache is not None and now < _jwks_expires_at:
        return _jwks_cache
    if now < _keycloak_circuit_open_until and _jwks_cache is None:
        raise KeycloakUnavailableError("Keycloak circuit breaker is open")

    async with _jwks_lock:
        now = time.monotonic()
        if _jwks_cache is not None and now < _jwks_expires_at:
            return _jwks_cache

        url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
        try:
            timeout = httpx.Timeout(settings.http_client_timeout_seconds)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                _jwks_cache = resp.json()
                _jwks_expires_at = now + settings.jwks_cache_ttl_seconds
                _keycloak_failure_count = 0
                _keycloak_circuit_open_until = 0.0
                return _jwks_cache
        except httpx.HTTPError as exc:
            # Use stale cache if present during transient Keycloak errors.
            if _jwks_cache is not None:
                return _jwks_cache
            _keycloak_failure_count += 1
            if _keycloak_failure_count >= settings.external_service_failure_threshold:
                _keycloak_circuit_open_until = now + settings.external_service_cooldown_seconds
            raise KeycloakUnavailableError("Failed to fetch Keycloak JWKS") from exc


def invalidate_jwks_cache() -> None:
    global _jwks_cache, _jwks_expires_at, _keycloak_failure_count, _keycloak_circuit_open_until
    _jwks_cache = None
    _jwks_expires_at = 0.0
    _keycloak_failure_count = 0
    _keycloak_circuit_open_until = 0.0


async def decode_jwt(token: str) -> dict:
    """Decode and validate a JWT token against Keycloak JWKS."""
    jwks = await fetch_jwks()
    issuer = settings.keycloak_issuer or f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
    expected_client = settings.keycloak_client_id
    try:
        header = jwt.get_unverified_header(token)
        key = None
        for k in jwks.get("keys", []):
            if k["kid"] == header.get("kid"):
                key = k
                break
        if key is None:
            raise JWTError("No matching key found")
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            issuer=issuer,
        )
        aud = payload.get("aud")
        aud_values = [aud] if isinstance(aud, str) else (aud or [])
        azp = payload.get("azp")
        if expected_client not in aud_values and azp != expected_client:
            raise JWTError("Token is not issued for expected client")
        return payload
    except JWTError:
        raise
