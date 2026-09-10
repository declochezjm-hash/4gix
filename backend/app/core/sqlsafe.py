from __future__ import annotations

import re

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def qualified_identifier(name: str) -> str:
    """Valide un identifiant SQL schéma.table (caractères sûrs uniquement)."""
    parts = [p.strip() for p in name.split(".") if p.strip()]
    if not parts or not all(_IDENT.match(part) for part in parts):
        raise ValueError(f"Identifiant SQL invalide: {name}")
    return ".".join(parts)


def simple_identifier(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"Identifiant SQL invalide: {name}")
    return name
