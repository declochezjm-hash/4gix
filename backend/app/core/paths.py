"""Résolution des chemins workspace 4GIx."""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


def resolve_workspace_path(raw_path: str | None, default: str | None = None) -> Path:
    value = (raw_path or default or "").strip()
    if not value:
        raise ValueError("Chemin de fichier manquant.")
    normalized = value.replace("\\", "/")
    workspace = Path(settings.workspace_dir)
    if normalized.startswith("/workspace/"):
        rel = normalized[len("/workspace/") :].lstrip("/")
        return (workspace / rel).resolve()
    path = Path(value)
    if not path.is_absolute():
        return (workspace / path).resolve()
    return path.resolve()


def workspace_subdir(*parts: str, create: bool = True) -> Path:
    path = Path(settings.workspace_dir).joinpath(*parts)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
