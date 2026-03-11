from datetime import UTC, datetime, timedelta
import base64
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from src.core import client_cert as client_cert_module


def _build_self_signed_cert(common_name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=30))
        .sign(private_key, hashes.SHA256())
    )
    return private_key, certificate


def test_get_jira_client_certificate_material_from_pkcs12(tmp_path, monkeypatch) -> None:
    private_key, certificate = _build_self_signed_cert("jira-client")
    bundle_path = tmp_path / "jira-client.p12"
    bundle_path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            name=b"jira-client",
            key=private_key,
            cert=certificate,
            cas=None,
            encryption_algorithm=serialization.BestAvailableEncryption(b"secret-pass"),
        )
    )

    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_path", str(bundle_path))
    monkeypatch.setattr(client_cert_module.settings, "jira_client_key_path", "")
    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_password", "secret-pass")
    client_cert_module.clear_jira_client_certificate_material_cache()

    material = client_cert_module.get_jira_client_certificate_material()

    assert material is not None
    assert material.key_path is not None
    assert "BEGIN CERTIFICATE" in Path(material.cert_path).read_text(encoding="utf-8")
    assert "PRIVATE KEY" in Path(material.key_path).read_text(encoding="utf-8")
    client_cert_module.clear_jira_client_certificate_material_cache()


def test_get_jira_client_certificate_material_from_pem_pair(tmp_path, monkeypatch) -> None:
    private_key, certificate = _build_self_signed_cert("jira-client")
    cert_path = tmp_path / "jira-client.crt.pem"
    key_path = tmp_path / "jira-client.key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_path", str(cert_path))
    monkeypatch.setattr(client_cert_module.settings, "jira_client_key_path", str(key_path))
    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_password", "")
    client_cert_module.clear_jira_client_certificate_material_cache()

    material = client_cert_module.get_jira_client_certificate_material()

    assert material == client_cert_module.ClientCertificateMaterial(
        cert_path=str(cert_path),
        key_path=str(key_path),
    )
    client_cert_module.clear_jira_client_certificate_material_cache()


def test_get_jira_client_certificate_material_from_vault_pkcs12(monkeypatch) -> None:
    private_key, certificate = _build_self_signed_cert("jira-client")
    bundle_bytes = pkcs12.serialize_key_and_certificates(
        name=b"jira-client",
        key=private_key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(b"secret-pass"),
    )

    monkeypatch.setattr(client_cert_module.settings, "vault_jira_client_cert_secret_path", "gendwh/jira/client-cert")
    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_path", "")
    monkeypatch.setattr(client_cert_module.settings, "jira_client_key_path", "")
    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_password", "")
    monkeypatch.setattr(
        client_cert_module,
        "get_vault_secret",
        lambda path: {
            "p12_base64": base64.b64encode(bundle_bytes).decode("ascii"),
            "password": "secret-pass",
            "filename": "jira-client.p12",
        },
    )
    client_cert_module.clear_jira_client_certificate_material_cache()

    material = client_cert_module.get_jira_client_certificate_material()

    assert material is not None
    assert material.key_path is not None
    assert "BEGIN CERTIFICATE" in Path(material.cert_path).read_text(encoding="utf-8")
    assert "PRIVATE KEY" in Path(material.key_path).read_text(encoding="utf-8")
    client_cert_module.clear_jira_client_certificate_material_cache()


def test_get_jira_client_certificate_material_from_vault_pem(monkeypatch) -> None:
    private_key, certificate = _build_self_signed_cert("jira-client")
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    monkeypatch.setattr(client_cert_module.settings, "vault_jira_client_cert_secret_path", "gendwh/jira/client-cert")
    monkeypatch.setattr(client_cert_module.settings, "jira_client_cert_path", "")
    monkeypatch.setattr(client_cert_module.settings, "jira_client_key_path", "")
    monkeypatch.setattr(
        client_cert_module,
        "get_vault_secret",
        lambda path: {
            "cert_pem": cert_pem,
            "key_pem": key_pem,
        },
    )
    client_cert_module.clear_jira_client_certificate_material_cache()

    material = client_cert_module.get_jira_client_certificate_material()

    assert material is not None
    assert material.key_path is not None
    assert "BEGIN CERTIFICATE" in Path(material.cert_path).read_text(encoding="utf-8")
    assert "PRIVATE KEY" in Path(material.key_path).read_text(encoding="utf-8")
    client_cert_module.clear_jira_client_certificate_material_cache()
