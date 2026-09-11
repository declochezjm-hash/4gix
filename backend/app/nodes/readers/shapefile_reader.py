from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd

from app.core.paths import resolve_workspace_path
from app.core.readers.shapefile import shapefile_read_outputs
from app.nodes.base import Base4GIxNode

SHAPEFILE_SIDECAR = (".shx", ".dbf", ".prj", ".cpg")


def _pick_shapefile_set(
    sets: List[Dict[str, Any]],
    layer_name: Optional[str],
) -> Dict[str, Any]:
    if not sets:
        raise ValueError("Archive .zip sans Shapefile complet (.shp + .shx + .dbf).")
    if layer_name:
        key = layer_name.strip().lower()
        for item in sets:
            if item.get("layer_name", "").lower() == key:
                return item
            stem = Path(str(item.get("stem", ""))).name.lower()
            if stem == key:
                return item
    return sets[0]


def _read_shapefile_path(path: Path, encoding: Optional[str]) -> gpd.GeoDataFrame:
    """Lit un .shp ; restaure .shx si absent (fichier .shp seul importé)."""
    os.environ.setdefault("SHAPE_RESTORE_SHX", "YES")
    kwargs: Dict[str, Any] = {}
    if encoding:
        kwargs["encoding"] = encoding
    try:
        return gpd.read_file(path, **kwargs)
    except Exception as exc:
        if path.suffix.lower() != ".shp":
            raise
        missing = [
            ext
            for ext in SHAPEFILE_SIDECAR
            if ext in (".shx", ".dbf") and not path.with_suffix(ext).is_file()
        ]
        if missing:
            raise ValueError(
                f"Shapefile incomplet ({path.name}) : manque {', '.join(missing)}. "
                "Glissez une archive .zip contenant .shp, .shx et .dbf (recommandé).",
            ) from exc
        raise


class ShapefileReader(Base4GIxNode):
    node_type = "shapefile_reader"
    category = "Reader"
    is_spatial = True
    label = "Shapefile Reader"
    description = "Lit un Shapefile (.shp) ou une archive .zip contenant un Shapefile."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Shapefile Reader",
            "description": "Source ESRI Shapefile (fichier .shp ou archive .zip).",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Chemin .shp",
                    "description": "Chemin extrait dans /workspace ou URI zip://…",
                    "default": "/workspace/imports/sample/layer.shp",
                },
                "zip_path": {
                    "type": "string",
                    "title": "Archive .zip source (optionnel)",
                    "description": "Chemin de l'archive d'origine si import drag-and-drop.",
                },
                "layer_name": {
                    "type": "string",
                    "title": "Nom de couche",
                },
                "encoding": {
                    "type": "string",
                    "title": "Encodage attributs (.cpg)",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = (params.get("path") or params.get("zip_path") or "").strip()
        if not raw_path:
            raise ValueError("Paramètre `path` manquant pour Shapefile Reader.")

        path = resolve_workspace_path(raw_path)
        layer_name = (params.get("layer_name") or "").strip() or None
        encoding = (params.get("encoding") or "").strip() or None

        if path.suffix.lower() == ".zip":
            from app.core.shapefile_import import (
                _extract_shapefile_sidecars,
                _geojson_payload,
                _read_geodataframe,
                discover_shapefile_sets,
                list_zip_entries,
            )

            if not path.is_file():
                raise FileNotFoundError(f"Archive Shapefile introuvable: {path}")
            entries = list_zip_entries(path.read_bytes())
            sets = discover_shapefile_sets(entries)
            chosen = _pick_shapefile_set(sets, layer_name)
            inner_shp = chosen["shp_path_in_zip"]
            shp_file = _extract_shapefile_sidecars(path, inner_shp)
            gdf = _read_geodataframe(shp_file)
            geojson, map_geojson, meta = _geojson_payload(gdf)
            meta["zip_path"] = str(path)
            return {
                "data": geojson,
                "map_geojson": map_geojson,
                "metadata": meta,
            }

        if not path.is_file():
            raise FileNotFoundError(
                f"Shapefile introuvable: {path} (vérifiez le chemin /workspace ou réimportez le fichier).",
            )

        gdf = _read_shapefile_path(path, encoding)
        geojson, map_geojson, meta = shapefile_read_outputs(gdf)
        meta.update(
            {
                "source": "shapefile",
                "path": str(path),
                "zip_path": params.get("zip_path"),
                "layer_name": params.get("layer_name"),
            },
        )
        return {
            "data": geojson,
            "map_geojson": map_geojson,
            "metadata": meta,
        }
