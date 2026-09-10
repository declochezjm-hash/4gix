"""Téléversement de fichiers de données spatiales (workspace 4GIx)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings
from app.core.paths import workspace_subdir
from app.core.shapefile_import import _safe_upload_name, validate_zip_shapefile

GEOTIFF_SUFFIXES = {".tif", ".tiff", ".geotiff"}
GEOJSON_SUFFIXES = {".geojson", ".json"}


def workspace_uri(path: Path) -> str:
    """Chemin logique /workspace/… pour les paramètres des nœuds Reader."""
    base = Path(settings.workspace_dir).resolve()
    resolved = path.resolve()
    try:
        rel = resolved.relative_to(base)
    except ValueError:
        return str(resolved)
    return f"/workspace/{rel.as_posix()}"


def detect_data_type(filename: str, raw: bytes) -> str:
    lower = (filename or "").lower()
    suffix = Path(lower).suffix

    if suffix == ".zip":
        ok, _sets, _components = validate_zip_shapefile(raw)
        if ok:
            return "shapefile"
        raise ValueError(
            "Archive .zip sans Shapefile valide (.shp + .shx + .dbf).",
        )

    if suffix in GEOTIFF_SUFFIXES:
        return "geotiff"

    if suffix in GEOJSON_SUFFIXES:
        if suffix == ".json" and not _looks_like_geojson(raw):
            raise ValueError("Fichier .json non reconnu comme GeoJSON.")
        return "geojson"

    raise ValueError(
        "Format non supporté. Extensions acceptées : .zip (Shapefile), "
        ".geojson, .json (GeoJSON), .tif, .tiff, .geotiff.",
    )


def _looks_like_geojson(raw: bytes) -> bool:
    sample = raw[:65536].decode("utf-8", errors="ignore").strip()
    if not sample:
        return False
    try:
        parsed = json.loads(sample)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    kind = parsed.get("type")
    return kind in {"FeatureCollection", "Feature", "Geometry"}


def save_upload(raw: bytes, filename: str) -> Path:
    uploads = workspace_subdir("uploads", create=True)
    safe_name = _safe_upload_name(filename)
    dest = uploads / f"{uuid.uuid4().hex[:10]}-{safe_name}"
    dest.write_bytes(raw)
    return dest


def suggested_reader(detected_type: str, filename: str, stored: Path) -> Dict[str, Any]:
    ws_path = workspace_uri(stored)
    stem = Path(filename).stem or "couche"
    if detected_type == "shapefile":
        return {
            "node_type": "shapefile_reader",
            "label": f"Shapefile — {stem}",
            "params": {
                "path": ws_path,
                "zip_path": ws_path,
                "layer_name": stem,
                "encoding": "utf-8",
            },
        }
    if detected_type == "geojson":
        return {
            "node_type": "geojson_reader",
            "label": f"GeoJSON — {stem}",
            "params": {
                "path": ws_path,
                "use_sample": False,
                "geojson": "",
            },
        }
    if detected_type == "geotiff":
        return {
            "node_type": "geotiff_raster_reader",
            "label": f"GeoTIFF — {stem}",
            "params": {
                "path": ws_path,
                "band": 1,
            },
        }
    raise ValueError(f"Type de données inconnu: {detected_type}")


def process_upload(raw: bytes, filename: str) -> Dict[str, Any]:
    if not raw:
        raise ValueError("Fichier vide.")
    detected_type = detect_data_type(filename, raw)
    stored = save_upload(raw, filename)
    suggested = suggested_reader(detected_type, filename, stored)
    return {
        "filename": Path(filename).name,
        "filepath": str(stored.resolve()),
        "workspace_path": workspace_uri(stored),
        "detected_type": detected_type,
        "suggested_node": suggested,
    }
