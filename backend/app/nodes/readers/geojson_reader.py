from __future__ import annotations

import json
from typing import Any, Dict, List

import geopandas as gpd

from app.core.paths import resolve_workspace_path
from app.core.readers.shapefile import shapefile_read_outputs
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


SAMPLE_WORKSPACE_DEMO = {
    "type": "FeatureCollection",
    "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Quartier Nord", "category": "urban", "group": "A"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.30, 48.86], [2.35, 48.86], [2.35, 48.89], [2.30, 48.89], [2.30, 48.86]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Quartier Sud", "category": "urban", "group": "A"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.30, 48.83], [2.35, 48.83], [2.35, 48.86], [2.30, 48.86], [2.30, 48.83]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Zone Est", "category": "urban", "group": "B"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.35, 48.84], [2.40, 48.84], [2.40, 48.88], [2.35, 48.88], [2.35, 48.84]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Bowtie", "category": "broken", "group": "X"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[2.41, 48.85], [2.43, 48.87], [2.41, 48.87], [2.43, 48.85], [2.41, 48.85]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Sans geometrie", "category": "broken", "group": "X"},
            "geometry": None,
        },
    ],
}


SAMPLE_REGIONS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Île-de-France", "code": "IDF"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1.4, 48.1], [3.6, 48.1], [3.6, 49.2], [1.4, 49.2], [1.4, 48.1]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Auvergne-Rhône-Alpes", "code": "ARA"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[3.6, 44.6], [7.2, 44.6], [7.2, 46.8], [3.6, 46.8], [3.6, 44.6]]],
            },
        },
        {
            "type": "Feature",
            "properties": {"name": "Provence-Alpes-Côte d'Azur", "code": "PAC"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[4.2, 42.9], [7.8, 42.9], [7.8, 44.9], [4.2, 44.9], [4.2, 42.9]]],
            },
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
                "sample_set": {
                    "type": "string",
                    "title": "Jeu d'exemple",
                    "enum": ["cities", "regions", "workspace_demo"],
                    "enumNames": ["Villes (points)", "Régions (polygones)", "Démo qualité géométrique (polygones + invalides)"],
                    "default": "cities",
                },
                "path": {
                    "type": "string",
                    "title": "Fichier GeoJSON",
                    "description": "Chemin dans /workspace (import drag-and-drop).",
                },
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
        file_path = (params.get("path") or "").strip()
        raw = (params.get("geojson") or "").strip()
        use_sample = params.get("use_sample", True)
        sample_set = params.get("sample_set") or "cities"
        if file_path:
            path = resolve_workspace_path(file_path)
            if not path.is_file():
                raise FileNotFoundError(f"GeoJSON introuvable: {path}")
            parsed = json.loads(path.read_text(encoding="utf-8"))
        elif raw:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        elif use_sample:
            if sample_set == "regions":
                parsed = SAMPLE_REGIONS
            elif sample_set in ("workspace_demo", "fme_demo"):
                parsed = SAMPLE_WORKSPACE_DEMO
            else:
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

        metadata: Dict[str, Any] = {
            "source": "geojson",
            "feature_count": len(fc.get("features") or []),
            "columns": columns,
            "crs": "EPSG:4326",
        }
        if file_path:
            metadata["path"] = str(resolve_workspace_path(file_path))

        result: Dict[str, Any] = {"data": fc, "metadata": metadata}
        if file_path and fc.get("features"):
            try:
                gdf = gpd.GeoDataFrame.from_features(
                    fc.get("features") or [],
                    crs="EPSG:4326",
                )
                _native, map_geojson, spatial_meta = shapefile_read_outputs(gdf)
                result["data"] = _native
                result["map_geojson"] = map_geojson
                metadata.update(
                    {k: v for k, v in spatial_meta.items() if k not in metadata},
                )
            except Exception:
                result["map_geojson"] = fc
                metadata.setdefault("bbox", None)
        return result
