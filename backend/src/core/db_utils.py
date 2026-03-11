"""Database utility helpers."""


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
