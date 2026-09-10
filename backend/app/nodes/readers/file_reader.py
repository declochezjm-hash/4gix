from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import geopandas as gpd

from app.core.config import settings
from app.nodes.base import Base4GIxNode


class FileReader(Base4GIxNode):
    node_type = "file_reader"
    category = "Reader"
    is_spatial = True
    label = "File Reader"
    description = "Lit un fichier vectoriel (GeoJSON, GeoPackage, Shapefile, CSV)."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "File Reader",
            "description": "Source fichier vectoriel.",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Chemin du fichier",
                    "description": "Chemin dans le workspace (/workspace) ou chemin absolu.",
                    "default": "/workspace/sample.geojson",
                },
                "layer": {
                    "type": "string",
                    "title": "Couche (GeoPackage / GDB)",
                },
                "encoding": {
                    "type": "string",
                    "title": "Encodage",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = params.get("path") or ""
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(settings.workspace_dir) / path
        if not path.exists():
            raise FileNotFoundError(f"Fichier introuvable: {path}")

        layer = params.get("layer") or None
        kwargs: Dict[str, Any] = {}
        if layer:
            kwargs["layer"] = layer
        gdf = gpd.read_file(path, **kwargs)
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        geojson = json.loads(gdf.to_json())
        return {
            "data": geojson,
            "metadata": {
                "source": "file",
                "path": str(path),
                "feature_count": len(gdf),
                "columns": [c for c in gdf.columns if c != "geometry"],
                "crs": str(gdf.crs) if gdf.crs else None,
                "geometry_types": sorted({str(t) for t in gdf.geom_type.dropna().unique()}),
            },
        }
