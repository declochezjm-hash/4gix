from __future__ import annotations

import json
from typing import Any, Dict, List

import geopandas as gpd

from app.nodes.base import (
    Base4GIxNode,
    _as_feature_collection,
    unwrap_named_input,
)


class SpatialJoinNode(Base4GIxNode):
    """Jointure spatiale entre deux flux (Input A / Input B) via GeoPandas."""

    node_type = "spatial_join"
    category = "Transformer"
    is_spatial = True
    label = "Spatial Join / Intersect"
    description = "Match features by location"
    input_handles: List[str] = ["input_a", "input_b"]

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Spatial Join",
            "description": "Reliez Input A (gauche) et Input B (droite), puis choisissez le prédicat.",
            "type": "object",
            "properties": {
                "predicate": {
                    "type": "string",
                    "title": "Opération spatiale",
                    "enum": ["intersects", "contains", "within", "touches", "overlaps"],
                    "enumNames": ["Intersects", "Contains", "Within", "Touches", "Overlaps"],
                    "default": "intersects",
                    "description": "Prédicat GeoPandas sjoin.",
                },
                "how": {
                    "type": "string",
                    "title": "Type de jointure",
                    "enum": ["inner", "left"],
                    "enumNames": ["Inner (intersection)", "Left (conserve A)"],
                    "default": "inner",
                },
                "suffix_b": {
                    "type": "string",
                    "title": "Suffixe colonnes B",
                    "default": "_b",
                    "description": "Suffixe ajouté aux champs de la couche B en cas de collision.",
                },
            },
            "required": ["predicate"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data_a = unwrap_named_input(inputs, "input_a")
        data_b = unwrap_named_input(inputs, "input_b")
        fc_a = _as_feature_collection(data_a)
        fc_b = _as_feature_collection(data_b)
        if fc_a is None:
            raise ValueError("Input A : aucune géométrie. Reliez un flux sur la poignée Input A.")
        if fc_b is None:
            raise ValueError("Input B : aucune géométrie. Reliez un flux sur la poignée Input B.")

        predicate = (params.get("predicate") or "intersects").lower()
        how = (params.get("how") or "inner").lower()
        suffix_b = params.get("suffix_b") or "_b"
        rsuffix = str(suffix_b).strip("_") or "b"
        allowed = {"intersects", "contains", "within", "touches", "overlaps"}
        if predicate not in allowed:
            raise ValueError(f"Prédicat spatial inconnu: {predicate}")

        left = gpd.GeoDataFrame.from_features(fc_a.get("features") or [], crs="EPSG:4326")
        right = gpd.GeoDataFrame.from_features(fc_b.get("features") or [], crs="EPSG:4326")
        if left.empty:
            raise ValueError("Input A est vide.")
        if right.empty:
            raise ValueError("Input B est vide.")
        if left.geometry.isna().all() or right.geometry.isna().all():
            raise ValueError("Les deux couches doivent contenir une géométrie.")

        joined = gpd.sjoin(left, right, how=how, predicate=predicate, lsuffix="a", rsuffix=rsuffix)
        if "index_right" in joined.columns:
            joined = joined.drop(columns=["index_right"])
        out = json.loads(joined.to_json())
        out["crs"] = fc_a.get("crs") or {"type": "name", "properties": {"name": "EPSG:4326"}}
        return {
            "data": out,
            "metadata": {
                "feature_count": len(joined),
                "input_a_count": len(left),
                "input_b_count": len(right),
                "predicate": predicate,
                "how": how,
                "operation": "spatial_join",
            },
        }
