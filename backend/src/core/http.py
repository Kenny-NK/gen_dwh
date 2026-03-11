"""Shared HTTP client TLS configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import ssl

import certifi

from src.core.config import settings


@lru_cache(maxsize=1)
def get_http_client_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    bundle_path = (settings.external_ca_bundle_path or "").strip()
    if not bundle_path:
        return context

    cert_path = Path(bundle_path)
    if not cert_path.is_file():
        raise FileNotFoundError(f"External CA bundle not found: {cert_path}")

    context.load_verify_locations(cafile=str(cert_path))
    return context
