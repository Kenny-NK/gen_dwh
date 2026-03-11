"""Helpers for loading client certificates for external services."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import base64
import hashlib
from pathlib import Path
import stat
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

from src.core.config import settings
from src.core.secret_manager import clear_vault_secret_cache, get_vault_secret


@dataclass(frozen=True)
class ClientCertificateMaterial:
    cert_path: str
    key_path: str | None = None

    def as_requests_cert(self) -> str | tuple[str, str]:
        if self.key_path:
            return self.cert_path, self.key_path
        return self.cert_path


def _read_password(raw_password: str | None) -> bytes | None:
    value = str(raw_password or "")
    if not value:
        return None
    return value.encode("utf-8")


def _secure_write(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def _temp_dir() -> Path:
    temp_dir = Path(tempfile.gettempdir()) / "gendwh-client-certs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def _materialize_pkcs12_bytes(
    raw_bytes: bytes,
    password: str | None,
    fingerprint_input: str,
) -> ClientCertificateMaterial:
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        raw_bytes,
        _read_password(password),
    )
    if private_key is None or certificate is None:
        raise ValueError("PKCS12 bundle does not contain both key and certificate")

    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:16]
    temp_dir = _temp_dir()

    pem_cert_path = temp_dir / f"jira-client-{fingerprint}.crt.pem"
    pem_key_path = temp_dir / f"jira-client-{fingerprint}.key.pem"

    cert_payload = certificate.public_bytes(serialization.Encoding.PEM)
    for extra_cert in additional_certificates or []:
        cert_payload += extra_cert.public_bytes(serialization.Encoding.PEM)

    key_payload = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    _secure_write(pem_cert_path, cert_payload)
    _secure_write(pem_key_path, key_payload)
    return ClientCertificateMaterial(cert_path=str(pem_cert_path), key_path=str(pem_key_path))


def _materialize_pkcs12(cert_path: Path, password: str | None) -> ClientCertificateMaterial:
    raw_bytes = cert_path.read_bytes()
    fingerprint_input = f"{cert_path}:{cert_path.stat().st_mtime_ns}:{cert_path.stat().st_size}"
    return _materialize_pkcs12_bytes(raw_bytes, password, fingerprint_input)


def _materialize_vault_pem(
    *,
    cert_pem: str,
    key_pem: str | None,
    fingerprint_input: str,
) -> ClientCertificateMaterial:
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()[:16]
    temp_dir = _temp_dir()
    cert_path = temp_dir / f"jira-client-{fingerprint}.crt.pem"
    _secure_write(cert_path, cert_pem.encode("utf-8"))
    if not key_pem:
        return ClientCertificateMaterial(cert_path=str(cert_path))
    key_path = temp_dir / f"jira-client-{fingerprint}.key.pem"
    _secure_write(key_path, key_pem.encode("utf-8"))
    return ClientCertificateMaterial(cert_path=str(cert_path), key_path=str(key_path))


def _load_from_vault() -> ClientCertificateMaterial | None:
    secret_path = str(settings.vault_jira_client_cert_secret_path or "").strip()
    if not secret_path:
        return None

    secret = get_vault_secret(secret_path)
    cert_field = str(settings.vault_jira_client_cert_field or "p12_base64").strip()
    cert_pem_field = str(settings.vault_jira_client_cert_pem_field or "cert_pem").strip()
    key_field = str(settings.vault_jira_client_key_field or "key_pem").strip()
    password_field = str(settings.vault_jira_client_cert_password_field or "password").strip()
    filename_field = str(settings.vault_jira_client_cert_filename_field or "filename").strip()

    password = str(secret.get(password_field) or "").strip() or settings.jira_client_cert_password
    cert_payload = str(secret.get(cert_field) or "").strip()
    cert_pem = str(secret.get(cert_pem_field) or "").strip()
    key_pem = str(secret.get(key_field) or "").strip()
    filename = str(secret.get(filename_field) or "vault-jira-client.p12").strip()

    if cert_payload:
        raw_bytes = base64.b64decode(cert_payload)
        fingerprint_input = f"vault:{secret_path}:{filename}:{len(raw_bytes)}"
        return _materialize_pkcs12_bytes(raw_bytes, password, fingerprint_input)

    if cert_pem:
        fingerprint_input = f"vault:{secret_path}:{len(cert_pem)}:{len(key_pem)}"
        return _materialize_vault_pem(
            cert_pem=cert_pem,
            key_pem=key_pem or None,
            fingerprint_input=fingerprint_input,
        )

    raise ValueError(f"Vault secret does not contain Jira client certificate material: {secret_path}")


@lru_cache(maxsize=1)
def get_jira_client_certificate_material() -> ClientCertificateMaterial | None:
    vault_material = _load_from_vault()
    if vault_material:
        return vault_material

    cert_path_value = str(settings.jira_client_cert_path or "").strip()
    key_path_value = str(settings.jira_client_key_path or "").strip()
    if not cert_path_value:
        return None

    cert_path = Path(cert_path_value)
    if not cert_path.is_file():
        raise FileNotFoundError(f"Jira client certificate file not found: {cert_path}")

    suffix = cert_path.suffix.lower()
    if suffix in {".p12", ".pfx"}:
        return _materialize_pkcs12(cert_path, settings.jira_client_cert_password)

    if key_path_value:
        key_path = Path(key_path_value)
        if not key_path.is_file():
            raise FileNotFoundError(f"Jira client private key file not found: {key_path}")
        return ClientCertificateMaterial(cert_path=str(cert_path), key_path=str(key_path))

    return ClientCertificateMaterial(cert_path=str(cert_path))


def get_http_client_cert() -> str | tuple[str, str] | None:
    material = get_jira_client_certificate_material()
    if not material:
        return None
    return material.as_requests_cert()


def clear_jira_client_certificate_material_cache() -> None:
    get_jira_client_certificate_material.cache_clear()
    clear_vault_secret_cache()
