from uuid import UUID, uuid4

from src.core.security import create_app_session_token, decode_app_session_token
from src.core.workspace_auth import (
    WorkspaceAccess,
    _build_auth_context_from_workspaces,
    extract_workspace_roles,
)
from src.models.user import User


def test_extract_workspace_roles_prefers_highest_priority_role() -> None:
    roles = {
        "workspace:finance:user",
        "workspace:finance:viewer",
        "workspace:sales:viewer",
        "system:admin",
    }

    result = extract_workspace_roles(roles)

    assert result == {"finance": "user", "sales": "viewer"}


def test_app_session_token_roundtrip_preserves_workspace_claims() -> None:
    user_id = uuid4()
    workspace_id = uuid4()

    token = create_app_session_token(
        subject="kc-user-123",
        user_id=str(user_id),
        email="user@example.com",
        active_workspace_id=str(workspace_id),
        is_system_admin=False,
    )
    payload = decode_app_session_token(token)

    assert payload["sub"] == "kc-user-123"
    assert UUID(payload["uid"]) == user_id
    assert UUID(payload["active_workspace_id"]) == workspace_id
    assert payload["email"] == "user@example.com"
    assert payload["is_system_admin"] is False


def test_build_auth_context_from_workspaces_uses_requested_workspace_role() -> None:
    workspace_id = uuid4()
    user = User(id=uuid4(), keycloak_id="kc-user-123", email="user@example.com", is_active=True)

    context = _build_auth_context_from_workspaces(
        user=user,
        roles={"workspace:acme:owner"},
        workspaces=[
            WorkspaceAccess(
                workspace_id=workspace_id,
                slug="acme",
                name="Acme",
                role="owner",
            )
        ],
        requested_workspace_id=workspace_id,
        is_system_admin=False,
    )

    assert context.active_workspace_id == workspace_id
    assert context.role == "owner"
    assert "flows:write" in context.permissions
