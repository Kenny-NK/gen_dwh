from src.services.audit_service import _escape_like_pattern


def test_escape_like_pattern_escapes_wildcards_and_backslashes() -> None:
    value = r"user_%\name"

    escaped = _escape_like_pattern(value)

    assert escaped == r"user\_\%\\name"
