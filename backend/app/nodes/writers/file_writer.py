from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import geopandas as gpd

from app.core.config import settings
from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data


class FileWriter(Base4GIxNode):
    node_type = "file_writer"
    category = "Writer"
    is_spatial = True
    label = "File Writer"
    description = "Écrit le résultat vers GeoJSON, GeoPackage ou CSV."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "File Writer",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Chemin de sortie",
                    "default": "/workspace/output.geojson",
                },
                "driver": {
                    "type": "string",
                    "title": "Format",
                    "enum": ["GeoJSON", "GPKG", "CSV"],
                    "default": "GeoJSON",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        if fc is None:
            raise ValueError("Aucune donnée à écrire.")

        raw_path = params.get("path") or "/workspace/output.geojson"
        path = Path(raw_path)
        if not path.is_absolute():
            path = Path(settings.workspace_dir) / path
        path.parent.mkdir(parents=True, exist_ok=True)
        driver = params.get("driver") or "GeoJSON"

        gdf = gpd.GeoDataFrame.from_features(fc.get("features") or [], crs="EPSG:4326")
        if driver == "CSV":
            df = gdf.drop(columns=["geometry"], errors="ignore")
            df.to_csv(path, index=False)
        else:
            gdf.to_file(path, driver=driver)

        return {
            "data": fc,
            "metadata": {
                "written": len(gdf),
                "path": str(path),
                "driver": driver,
            },
        }
