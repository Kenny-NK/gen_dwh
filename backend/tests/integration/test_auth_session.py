from uuid import UUID, uuid4

import pytest
from fastapi import Request

from src.core.workspace_auth import AuthContext, WorkspaceAccess


@pytest.mark.asyncio
async def test_create_session_accepts_valid_bearer_and_sets_cookie(client, monkeypatch) -> None:
    async def fake_decode_jwt(token: str) -> dict:
        assert token == "test-access-token"
        return {"sub": "kc-user-123", "email": "user@example.com"}

    async def fake_sync_auth_context_from_keycloak_payload(_: dict) -> AuthContext:
        return AuthContext(
            user_id=uuid4(),
            sub="kc-user-123",
            email="user@example.com",
            is_system_admin=False,
            roles=["workspace:acme:owner"],
            active_workspace_id=uuid4(),
            role="owner",
            permissions=["flows:write"],
            workspaces=[
                WorkspaceAccess(
                    workspace_id=uuid4(),
                    slug="acme",
                    name="Acme",
                    role="owner",
                )
            ],
        )

    monkeypatch.setattr("src.api.v1.auth.decode_jwt", fake_decode_jwt)
    monkeypatch.setattr(
        "src.api.v1.auth.sync_auth_context_from_keycloak_payload",
        fake_sync_auth_context_from_keycloak_payload,
    )

    response = await client.post(
        "/api/v1/auth/session",
        headers={"Authorization": "Bearer test-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.cookies.get("gendwh_access_token")


@pytest.mark.asyncio
async def test_auth_me_uses_read_only_bearer_loader(client, monkeypatch) -> None:
    async def fake_decode_jwt(token: str) -> dict:
        assert token == "test-access-token"
        return {"sub": "kc-user-123", "email": "user@example.com"}

    async def fake_load_auth_context_from_keycloak_payload(_: dict) -> AuthContext:
        workspace_id = uuid4()
        return AuthContext(
            user_id=uuid4(),
            sub="kc-user-123",
            email="user@example.com",
            is_system_admin=False,
            roles=["workspace:acme:owner"],
            active_workspace_id=workspace_id,
            role="owner",
            permissions=["flows:write"],
            workspaces=[
                WorkspaceAccess(
                    workspace_id=workspace_id,
                    slug="acme",
                    name="Acme",
                    role="owner",
                )
            ],
        )

    monkeypatch.setattr("src.middleware.auth.decode_jwt", fake_decode_jwt)
    monkeypatch.setattr(
        "src.middleware.auth.load_auth_context_from_keycloak_payload",
        fake_load_auth_context_from_keycloak_payload,
    )

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer test-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_create_session_preserves_selected_workspace_from_existing_cookie(client, monkeypatch) -> None:
    preserved_workspace_id = uuid4()
    secondary_workspace_id = uuid4()

    async def fake_decode_jwt(token: str) -> dict:
        assert token == "test-access-token"
        return {"sub": "kc-user-123", "email": "user@example.com"}

    async def fake_sync_auth_context_from_keycloak_payload(_: dict) -> AuthContext:
        return AuthContext(
            user_id=uuid4(),
            sub="kc-user-123",
            email="user@example.com",
            is_system_admin=False,
            roles=["workspace:acme:owner", "workspace:beta:user"],
            active_workspace_id=None,
            role="viewer",
            permissions=["flows:read"],
            workspaces=[
                WorkspaceAccess(
                    workspace_id=preserved_workspace_id,
                    slug="acme",
                    name="Acme",
                    role="owner",
                ),
                WorkspaceAccess(
                    workspace_id=secondary_workspace_id,
                    slug="beta",
                    name="Beta",
                    role="user",
                ),
            ],
        )

    monkeypatch.setattr("src.api.v1.auth.decode_jwt", fake_decode_jwt)
    monkeypatch.setattr(
        "src.api.v1.auth.sync_auth_context_from_keycloak_payload",
        fake_sync_auth_context_from_keycloak_payload,
    )

    monkeypatch.setattr(
        "src.api.v1.auth._preserved_workspace_id",
        lambda request, current_user: preserved_workspace_id,
    )

    response = await client.post(
        "/api/v1/auth/session",
        headers={"Authorization": "Bearer test-access-token"},
    )

    assert response.status_code == 200
    assert response.json()["requires_workspace_selection"] is False
    assert response.json()["active_workspace_id"] == str(preserved_workspace_id)


def test_preserved_workspace_id_supports_auth_context_workspace_shape() -> None:
    from src.api.v1.auth import _preserved_workspace_id
    from src.core.security import create_app_session_token

    workspace_id = uuid4()
    token = create_app_session_token(
        subject="kc-user-123",
        user_id=str(uuid4()),
        email="user@example.com",
        active_workspace_id=str(workspace_id),
        is_system_admin=False,
    )

    scope = {
        "type": "http",
        "headers": [(b"cookie", f"gendwh_access_token={token}".encode())],
    }
    request = Request(scope)
    current_user = {
        "active_workspace_id": None,
        "workspaces": [
            {
                "workspace_id": workspace_id,
                "slug": "acme",
                "name": "Acme",
                "role": "owner",
            }
        ],
    }

    preserved = _preserved_workspace_id(request, current_user)

    assert preserved == workspace_id
