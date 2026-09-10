from __future__ import annotations

import json
from typing import Any, Dict, List

from app.nodes.base import Base4GIxNode, _as_feature_collection


SAMPLE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Paris", "population": 2148000},
            "geometry": {"type": "Point", "coordinates": [2.3522, 48.8566]},
        },
        {
            "type": "Feature",
            "properties": {"name": "Lyon", "population": 522000},
            "geometry": {"type": "Point", "coordinates": [4.8357, 45.7640]},
        },
        {
            "type": "Feature",
            "properties": {"name": "Marseille", "population": 870000},
            "geometry": {"type": "Point", "coordinates": [5.3698, 43.2965]},
        },
    ],
}


class GeoJSONReader(Base4GIxNode):
    node_type = "geojson_reader"
    category = "Reader"
    is_spatial = True
    label = "GeoJSON Reader"
    description = "Parse un GeoJSON inline ou utilise le jeu d'exemple 4GIx."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "GeoJSON Reader",
            "description": "Source GeoJSON inline.",
            "type": "object",
            "properties": {
                "geojson": {
                    "type": "string",
                    "title": "GeoJSON",
                    "format": "textarea",
                    "description": "FeatureCollection ou Feature. Vide = jeu d'exemple.",
                },
                "use_sample": {
                    "type": "boolean",
                    "title": "Utiliser le jeu d'exemple",
                    "default": True,
                },
            },
            "required": [],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        raw = (params.get("geojson") or "").strip()
        use_sample = params.get("use_sample", True)
        if raw:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        elif use_sample:
            parsed = SAMPLE_GEOJSON
        else:
            parsed = {"type": "FeatureCollection", "features": []}

        fc = _as_feature_collection(parsed)
        if fc is None:
            raise ValueError("Le contenu fourni n'est pas un GeoJSON valide.")

        columns: List[str] = []
        for feature in fc.get("features") or []:
            for key in (feature.get("properties") or {}).keys():
                if key not in columns:
                    columns.append(key)

        return {
            "data": fc,
            "metadata": {
                "source": "geojson",
                "feature_count": len(fc.get("features") or []),
                "columns": columns,
                "crs": "EPSG:4326",
            },
        }
