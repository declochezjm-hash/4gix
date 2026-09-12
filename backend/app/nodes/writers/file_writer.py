from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from app.core.config import settings
from app.core.readers.tabular import find_xy_columns
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
        if (
            hasattr(gdf, "geometry")
            and (gdf.geometry.isna().all() or "geometry" not in gdf.columns)
            and len(gdf) > 0
        ):
            pair = find_xy_columns([str(c) for c in gdf.columns])
            if pair:
                x_col, y_col = pair
                work = gdf.copy()
                work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
                work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
                work = work.dropna(subset=[x_col, y_col])
                geometry = [
                    Point(xy) for xy in zip(work[x_col], work[y_col], strict=True)
                ]
                attrs = work.drop(columns=[x_col, y_col], errors="ignore")
                gdf = gpd.GeoDataFrame(attrs, geometry=geometry, crs="EPSG:4326")

        spatial_driver = driver not in {"CSV", None}
        no_geom = (
            not hasattr(gdf, "geometry")
            or gdf.geometry.isna().all()
            or "geometry" not in gdf.columns
        )
        if spatial_driver and no_geom:
            driver = "CSV"
            path = path.with_suffix(".csv")

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
