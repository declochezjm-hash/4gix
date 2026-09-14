from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from app.core.config import settings
from app.core.crs import normalize_crs
from app.core.readers.tabular import find_xy_columns
from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data


class FileWriter(Base4GIxNode):
    node_type = "file_writer"
    category = "Writer"
    is_spatial = True
    label = "File Writer"
    description = (
        "Écrit le résultat sur le serveur puis propose le téléchargement "
        "(emplacement et nom choisis dans le navigateur)."
    )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "File Writer",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier de sortie",
                    "format": "output_path",
                    "description": (
                        "Nom du fichier produit. Utilisez « Parcourir… » pour "
                        "choisir l'emplacement et le nom avant l'exécution."
                    ),
                    "default": "/workspace/exports/output.geojson",
                },
                "driver": {
                    "type": "string",
                    "title": "Format",
                    "enum": ["GeoJSON", "GPKG", "CSV", "ESRI Shapefile"],
                    "enumNames": [
                        "GeoJSON",
                        "GeoPackage",
                        "CSV",
                        "Shapefile (.shp)",
                    ],
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

        features = fc.get("features") or []
        crs_value = normalize_crs(params.get("crs") or fc.get("crs"))
        gdf = gpd.GeoDataFrame.from_features(
            features,
            crs=crs_value if features else None,
        )
        if (
            len(gdf) > 0
            and (
                "geometry" not in gdf.columns
                or gdf.geometry.isna().all()
            )
        ):
            prop_rows = [
                dict(f.get("properties") or {})
                for f in features
                if isinstance(f, dict)
            ]
            pair = find_xy_columns([str(c) for c in gdf.columns])
            if not pair and prop_rows:
                pair = find_xy_columns([str(k) for k in prop_rows[0].keys()])
            if pair:
                x_col, y_col = pair
                work = pd.DataFrame(prop_rows) if prop_rows else gdf.copy()
                work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
                work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
                work = work.dropna(subset=[x_col, y_col])
                geometry = [
                    Point(xy) for xy in zip(work[x_col], work[y_col], strict=True)
                ]
                attrs = work.drop(columns=[x_col, y_col], errors="ignore")
                gdf = gpd.GeoDataFrame(attrs, geometry=geometry, crs="EPSG:4326")

        spatial_driver = str(driver or "").upper() not in {"CSV", ""}
        no_geom = (
            not hasattr(gdf, "geometry")
            or "geometry" not in gdf.columns
            or gdf.geometry.isna().all()
        )
        if spatial_driver and no_geom:
            driver = "CSV"
            path = path.with_suffix(".csv")

        if driver == "CSV":
            df = gdf.drop(columns=["geometry"], errors="ignore")
            df.to_csv(path, index=False)
        else:
            if gdf.crs is None:
                gdf = gdf.set_crs(crs_value)
            else:
                gdf = gdf.set_crs(normalize_crs(gdf.crs))
            gdf.to_file(path, driver=driver)

        workspace_root = Path(settings.workspace_dir).resolve()
        try:
            rel = path.resolve().relative_to(workspace_root)
            logical_path = f"/workspace/{rel.as_posix()}"
        except ValueError:
            logical_path = str(path)

        return {
            "data": fc,
            "metadata": {
                "written": len(gdf),
                "path": logical_path,
                "workspace_path": logical_path,
                "driver": driver,
                "download_ready": True,
            },
        }
