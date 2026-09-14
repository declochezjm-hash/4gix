"""Stockage local des credentials (workspace) — liste sans secrets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.db import new_uuid
from app.core.paths import workspace_subdir

_STORE_NAME = "credentials.json"


def _store_path() -> Path:
    return workspace_subdir(".4gix", create=True) / _STORE_NAME


def _load() -> List[Dict[str, Any]]:
    path = _store_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save(rows: List[Dict[str, Any]]) -> None:
    path = _store_path()
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def list_credentials(credential_type: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = _load()
    out: List[Dict[str, Any]] = []
    for row in rows:
        if credential_type and row.get("type") != credential_type:
            continue
        out.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "type": row.get("type"),
                "created_at": row.get("created_at"),
            }
        )
    return out


def create_credential(
    name: str,
    credential_type: str,
    secret: str = "",
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("name_required")
    credential_type = (credential_type or "").strip()
    if not credential_type:
        raise ValueError("type_required")

    rows = _load()
    row = {
        "id": new_uuid(),
        "name": name,
        "type": credential_type,
        "secret": secret,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    rows.append(row)
    _save(rows)
    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "created_at": row["created_at"],
    }
