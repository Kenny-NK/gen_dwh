"""PII detection and masking service (T055, T062)."""

import re
from typing import Any

PII_PATTERNS: dict[str, re.Pattern] = {
    "pii_email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "pii_phone": re.compile(r"\+7[0-9]{10}|8[0-9]{10}"),
    "pii_credit_card": re.compile(r"\b[0-9]{13,19}\b"),
    "pii_passport": re.compile(r"\b[0-9]{4}\s?[0-9]{6}\b"),
}

MASK_RULES: dict[str, callable] = {
    "pii_email": lambda v: v[0] + "***@" + v.split("@")[1] if "@" in str(v) else "***",
    "pii_phone": lambda v: str(v)[:3] + "***" + str(v)[6:9] + "**" + str(v)[-2:] if len(str(v)) >= 11 else "***",
    "pii_credit_card": lambda v: "****" + str(v)[-4:],
    "pii_passport": lambda v: "****" + str(v)[-4:],
    "sensitive": lambda v: "***",
}


def mask_value(value: Any, sensitivity_type: str) -> str | None:
    """Mask a value based on its sensitivity type."""
    if value is None:
        return None
    mask_fn = MASK_RULES.get(sensitivity_type, MASK_RULES["sensitive"])
    try:
        return mask_fn(value)
    except Exception:
        return "***"


def mask_row(row: dict, sensitive_columns: dict[str, str]) -> dict:
    """Mask sensitive columns in a row."""
    result = dict(row)
    for col_name, sensitivity_type in sensitive_columns.items():
        if col_name in result:
            result[col_name] = mask_value(result[col_name], sensitivity_type)
    return result
