"""Création de géométrie Point à partir de colonnes X/Y ou lon/lat (style FME VertexCreator)."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from app.core.readers.tabular import find_xy_columns
from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data
from app.nodes.workflow_features import input_features


def _features_from_properties_rows(
    rows: List[Dict[str, Any]],
    x_col: str,
    y_col: str,
    crs: str,
) -> Dict[str, Any]:
    work = pd.DataFrame(rows)
    if x_col not in work.columns or y_col not in work.columns:
        raise ValueError(
            f"Colonnes {x_col}/{y_col} introuvables pour créer la géométrie."
        )
    work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work.dropna(subset=[x_col, y_col])
    geometry = [Point(xy) for xy in zip(work[x_col], work[y_col], strict=True)]
    attrs = work.drop(columns=[x_col, y_col], errors="ignore")
    gdf = gpd.GeoDataFrame(attrs, geometry=geometry, crs=crs)
    fc = json.loads(gdf.to_json())
    if isinstance(fc, dict):
        fc["crs"] = crs
        return fc
    return {"type": "FeatureCollection", "features": [], "crs": crs}


class VertexCreatorNode(Base4GIxNode):
    node_type = "vertex_creator"
    category = "Transformer"
    is_spatial = True
    label = "Vertex Creator"
    description = "Crée des points à partir de colonnes X/Y ou longitude/latitude."
    palette_group = "Geometry"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Vertex Creator",
            "description": "Matérialise une colonne geometry (Point) depuis des coordonnées attributaires.",
            "type": "object",
            "properties": {
                "x_field": {"type": "string", "title": "Colonne X / Longitude"},
                "y_field": {"type": "string", "title": "Colonne Y / Latitude"},
                "target_crs": {
                    "type": "string",
                    "title": "CRS cible",
                    "default": "EPSG:4326",
                },
            },
            "required": ["x_field", "y_field"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        target_crs = str(params.get("target_crs") or "EPSG:4326")
        x_field = str(params.get("x_field") or "").strip()
        y_field = str(params.get("y_field") or "").strip()

        if fc is None:
            raise ValueError("Aucune donnée en entrée pour Vertex Creator.")

        features = fc.get("features") or []
        if not features:
            raise ValueError("Jeu vide — impossible de créer des sommets.")

        with_geom = [
            f
            for f in features
            if isinstance(f, dict)
            and isinstance(f.get("geometry"), dict)
            and f.get("geometry", {}).get("type")
        ]
        if len(with_geom) == len(features):
            return {
                "data": fc,
                "metadata": {
                    "operation": "vertex_creator",
                    "skipped": True,
                    "feature_count": len(features),
                },
            }

        if not x_field or not y_field:
            props_keys: List[str] = []
            sample = features[0].get("properties") if isinstance(features[0], dict) else {}
            if isinstance(sample, dict):
                props_keys = [str(k) for k in sample.keys()]
            pair = find_xy_columns(props_keys)
            if not pair:
                raise ValueError(
                    "Colonnes X/Y non détectées — renseignez x_field et y_field."
                )
            x_field, y_field = pair

        rows: List[Dict[str, Any]] = []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            props = dict(feature.get("properties") or {})
            geom = feature.get("geometry")
            if isinstance(geom, dict) and geom.get("type"):
                rows.append(props)
                continue
            if x_field in props and y_field in props:
                rows.append(props)

        if not rows:
            raise ValueError(
                "Aucune ligne exploitable pour créer la géométrie (colonnes XY vides)."
            )

        out_fc = _features_from_properties_rows(rows, x_field, y_field, target_crs)
        return {
            "data": out_fc,
            "metadata": {
                "operation": "vertex_creator",
                "x_field": x_field,
                "y_field": y_field,
                "target_crs": target_crs,
                "feature_count": len(out_fc.get("features") or []),
            },
        }


class CoordinateSetterNode(VertexCreatorNode):
    node_type = "coordinate_setter"
    label = "Coordinate Property Setter"
