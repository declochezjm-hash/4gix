"""Téléchargement sécurisé des fichiers produits dans le workspace."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Tuple

from fastapi import HTTPException

from app.core.config import settings
from app.core.paths import resolve_workspace_path
from app.core.shapefile_bundle import collect_shapefile_parts


def _workspace_root() -> Path:
    return Path(settings.workspace_dir).resolve()


def assert_workspace_file(logical_path: str) -> Path:
    path = resolve_workspace_path(logical_path)
    root = _workspace_root()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Chemin hors workspace.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Fichier introuvable dans le workspace.")
    return path


def shapefile_zip_bytes(shp_path: Path) -> bytes:
    parts = collect_shapefile_parts(shp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for part in parts.values():
            archive.write(part, arcname=part.name)
    return buffer.getvalue()


def workspace_download_payload(logical_path: str) -> Tuple[bytes, str, str]:
    """
    Retourne (contenu, nom de fichier suggéré, type MIME).
    Les Shapefiles sont livrés en archive .zip (sidecars inclus).
    """
    path = assert_workspace_file(logical_path)
    suffix = path.suffix.lower()
    if suffix == ".shp":
        stem = path.stem
        return (
            shapefile_zip_bytes(path),
            f"{stem}.zip",
            "application/zip",
        )
    mime = {
        ".geojson": "application/geo+json",
        ".json": "application/json",
        ".gpkg": "application/geopackage+sqlite3",
        ".csv": "text/csv",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(suffix, "application/octet-stream")
    return path.read_bytes(), path.name, mime
