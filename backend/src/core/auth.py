"""Keycloak OIDC client (T019)."""

import httpx

from src.core.config import settings


class KeycloakClient:
    """Client for Keycloak OIDC operations."""

    def __init__(self) -> None:
        self.base_url = f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"

    @property
    def token_url(self) -> str:
        return f"{self.base_url}/protocol/openid-connect/token"

    @property
    def userinfo_url(self) -> str:
        return f"{self.base_url}/protocol/openid-connect/userinfo"

    @property
    def jwks_url(self) -> str:
        return f"{self.base_url}/protocol/openid-connect/certs"

    async def get_userinfo(self, access_token: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()


keycloak_client = KeycloakClient()
