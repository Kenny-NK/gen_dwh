"""Helpers for flattening nested API records into table-friendly columns."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

_MAX_IDENTIFIER_LEN = 63
_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9_]+")


def normalize_identifier(
    raw_value: str | None,
    fallback: str,
    *,
    digit_prefix: str = "c_",
) -> str:
    value = _IDENTIFIER_RE.sub("_", (raw_value or "").strip().lower()).strip("_")
    if not value:
        value = fallback
    if value[0].isdigit():
        value = f"{digit_prefix}{value}"
    return value[:_MAX_IDENTIFIER_LEN]


def stringify_flat_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text or None


def flatten_record(record: dict[str, Any]) -> dict[str, str | None]:
    flattened: dict[str, str | None] = {}
    seen: set[str] = set()

    def reserve(raw_key: str) -> str:
        base = normalize_identifier(raw_key, "field")
        candidate = base
        suffix = 1
        while candidate in seen:
            tail = f"_{suffix}"
            candidate = f"{base[: _MAX_IDENTIFIER_LEN - len(tail)]}{tail}"
            suffix += 1
        seen.add(candidate)
        return candidate

    def visit(path: str, value: Any) -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                child_name = f"{path}_{child_key}" if path else str(child_key)
                visit(child_name, child_value)
            return

        column = reserve(path)
        flattened[column] = stringify_flat_value(value)

    for raw_key, raw_value in record.items():
        visit(str(raw_key), raw_value)

    return flattened
