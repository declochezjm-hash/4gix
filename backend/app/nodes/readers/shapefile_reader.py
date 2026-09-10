from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import geopandas as gpd

from app.core.config import settings
from app.nodes.base import Base4GIxNode


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
        raw_path = (params.get("path") or "").strip()
        if not raw_path:
            raise ValueError("Paramètre `path` manquant pour Shapefile Reader.")

        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(settings.workspace_dir) / path

        if path.suffix.lower() == ".zip":
            from app.core.shapefile_import import (
                _extract_shapefile_sidecars,
                _geojson_payload,
                _read_geodataframe,
                discover_shapefile_sets,
                list_zip_entries,
            )

            entries = list_zip_entries(path.read_bytes())
            sets = discover_shapefile_sets(entries)
            if not sets:
                raise ValueError("Archive .zip sans Shapefile complet (.shp + .shx + .dbf).")
            inner_shp = sets[0]["shp_path_in_zip"]
            shp_file = _extract_shapefile_sidecars(path, inner_shp)
            gdf = _read_geodataframe(shp_file)
            geojson, meta = _geojson_payload(gdf)
            meta["zip_path"] = str(path)
            return {"data": geojson, "metadata": meta}

        if not path.is_file():
            raise FileNotFoundError(f"Shapefile introuvable: {path}")

        gdf = gpd.read_file(path, encoding=params.get("encoding") or None)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        geojson = json.loads(gdf.to_json())
        return {
            "data": geojson,
            "metadata": {
                "source": "shapefile",
                "path": str(path),
                "zip_path": params.get("zip_path"),
                "layer_name": params.get("layer_name"),
                "feature_count": len(gdf),
                "columns": [col for col in gdf.columns if col != "geometry"],
                "crs": str(gdf.crs) if gdf.crs else None,
                "geometry_types": sorted(
                    {str(value) for value in gdf.geom_type.dropna().unique()},
                ),
            },
        }
