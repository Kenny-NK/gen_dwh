import httpx
import pytest

from src.core import secret_manager as secret_manager_module


def test_get_vault_secret_reads_kv_v2_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": {"data": {"p12_base64": "abc", "password": "secret"}}}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["verify"] = kwargs.get("verify")
            captured["headers"] = kwargs.get("headers")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str) -> DummyResponse:
            captured["url"] = url
            return DummyResponse()

    monkeypatch.setattr(secret_manager_module.settings, "vault_addr", "https://vault.example.local")
    monkeypatch.setattr(secret_manager_module.settings, "vault_auth_method", "token")
    monkeypatch.setattr(secret_manager_module.settings, "vault_token", "vault-token")
    monkeypatch.setattr(secret_manager_module.settings, "vault_kv_mount", "secret")
    monkeypatch.setattr(secret_manager_module.settings, "vault_kv_version", "v2")
    monkeypatch.setattr(secret_manager_module.settings, "external_ca_bundle_path", "")
    monkeypatch.setattr(secret_manager_module.httpx, "Client", DummyClient)
    secret_manager_module.clear_vault_secret_cache()

    secret = secret_manager_module.get_vault_secret("gendwh/jira/client-cert")

    assert secret == {"p12_base64": "abc", "password": "secret"}
    assert captured["url"] == "https://vault.example.local/v1/secret/data/gendwh/jira/client-cert"
    assert captured["headers"] == {"X-Vault-Token": "vault-token"}
    assert captured["verify"] is True
    secret_manager_module.clear_vault_secret_cache()


def test_get_vault_secret_uses_external_ca_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": {"data": {"value": "ok"}}}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            self.verify = kwargs.get("verify")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str) -> DummyResponse:
            return DummyResponse()

    monkeypatch.setattr(secret_manager_module.settings, "vault_addr", "https://vault.example.local")
    monkeypatch.setattr(secret_manager_module.settings, "vault_auth_method", "token")
    monkeypatch.setattr(secret_manager_module.settings, "vault_token", "vault-token")
    monkeypatch.setattr(secret_manager_module.settings, "vault_kv_mount", "secret")
    monkeypatch.setattr(secret_manager_module.settings, "vault_kv_version", "v2")
    monkeypatch.setattr(secret_manager_module.settings, "external_ca_bundle_path", "/tmp/external-ca.pem")
    monkeypatch.setattr(secret_manager_module.httpx, "Client", DummyClient)
    secret_manager_module.clear_vault_secret_cache()

    secret_manager_module.get_vault_secret("gendwh/jira/client-cert")

    secret_manager_module.clear_vault_secret_cache()


def test_get_vault_secret_rejects_unexpected_kv_v2_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"data": {"metadata": {}}}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def get(self, url: str) -> DummyResponse:
            return DummyResponse()

    monkeypatch.setattr(secret_manager_module.settings, "vault_addr", "https://vault.example.local")
    monkeypatch.setattr(secret_manager_module.settings, "vault_auth_method", "token")
    monkeypatch.setattr(secret_manager_module.settings, "vault_token", "vault-token")
    monkeypatch.setattr(secret_manager_module.settings, "vault_kv_mount", "secret")
    monkeypatch.setattr(secret_manager_module.settings, "vault_kv_version", "v2")
    monkeypatch.setattr(secret_manager_module.httpx, "Client", DummyClient)
    secret_manager_module.clear_vault_secret_cache()

    with pytest.raises(ValueError):
        secret_manager_module.get_vault_secret("gendwh/jira/client-cert")

    secret_manager_module.clear_vault_secret_cache()


def test_get_vault_client_token_uses_approle_login(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"auth": {"client_token": "approle-client-token"}}

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["verify"] = kwargs.get("verify")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, json: dict[str, str]) -> DummyResponse:
            captured["url"] = url
            captured["json"] = json
            return DummyResponse()

    monkeypatch.setattr(secret_manager_module.settings, "vault_addr", "https://vault.example.local")
    monkeypatch.setattr(secret_manager_module.settings, "vault_auth_method", "approle")
    monkeypatch.setattr(secret_manager_module.settings, "vault_approle_mount", "approle")
    monkeypatch.setattr(secret_manager_module.settings, "vault_role_id", "role-id")
    monkeypatch.setattr(secret_manager_module.settings, "vault_secret_id", "secret-id")
    monkeypatch.setattr(secret_manager_module.settings, "external_ca_bundle_path", "")
    monkeypatch.setattr(secret_manager_module.httpx, "Client", DummyClient)
    secret_manager_module.clear_vault_secret_cache()

    token = secret_manager_module.get_vault_client_token()

    assert token == "approle-client-token"
    assert captured["url"] == "https://vault.example.local/v1/auth/approle/login"
    assert captured["json"] == {"role_id": "role-id", "secret_id": "secret-id"}
    assert captured["verify"] is True
    secret_manager_module.clear_vault_secret_cache()


def test_get_vault_client_token_rejects_missing_approle_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secret_manager_module.settings, "vault_auth_method", "approle")
    monkeypatch.setattr(secret_manager_module.settings, "vault_role_id", "")
    monkeypatch.setattr(secret_manager_module.settings, "vault_secret_id", "")
    secret_manager_module.clear_vault_secret_cache()

    with pytest.raises(ValueError):
        secret_manager_module.get_vault_client_token()

    secret_manager_module.clear_vault_secret_cache()
