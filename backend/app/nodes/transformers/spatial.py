from __future__ import annotations

import json
from typing import Any, Dict

import geopandas as gpd
from shapely.geometry import shape

from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data


class ReprojectTransformer(Base4GIxNode):
    node_type = "reproject"
    category = "Transformer"
    is_spatial = True
    label = "Reprojection"
    description = "Reprojette une couche vers un système de coordonnées cible."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Reprojection",
            "type": "object",
            "properties": {
                "source_crs": {
                    "type": "string",
                    "title": "CRS source",
                    "format": "epsg",
                    "default": "EPSG:4326",
                },
                "target_crs": {
                    "type": "string",
                    "title": "CRS cible",
                    "format": "epsg",
                    "default": "EPSG:2154",
                    "description": "Ex. EPSG:2154 (Lambert-93), EPSG:3857 (Web Mercator).",
                },
            },
            "required": ["target_crs"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        if fc is None:
            raise ValueError("Aucune géométrie en entrée pour la reprojection.")

        source_crs = params.get("source_crs") or "EPSG:4326"
        target_crs = params.get("target_crs") or "EPSG:2154"
        gdf = gpd.GeoDataFrame.from_features(fc.get("features") or [], crs=source_crs)
        gdf = gdf.to_crs(target_crs)
        out = json.loads(gdf.to_json())
        out["crs"] = {"type": "name", "properties": {"name": target_crs}}
        return {
            "data": out,
            "metadata": {
                "feature_count": len(gdf),
                "crs": target_crs,
                "source_crs": source_crs,
            },
        }


class BufferTransformer(Base4GIxNode):
    node_type = "buffer"
    category = "Transformer"
    is_spatial = True
    label = "Buffer"
    description = "Calcule un tampon autour des géométries (unités du CRS courant)."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Buffer",
            "type": "object",
            "properties": {
                "distance": {
                    "type": "number",
                    "title": "Distance de buffer",
                    "format": "slider",
                    "default": 0.01,
                    "minimum": 0.001,
                    "maximum": 1,
                    "multipleOf": 0.001,
                    "description": "En degrés si CRS=4326, en mètres si CRS projeté.",
                },
                "resolution": {
                    "type": "integer",
                    "title": "Résolution",
                    "default": 16,
                },
            },
            "required": ["distance"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        if fc is None:
            raise ValueError("Aucune géométrie en entrée pour le buffer.")
        distance = float(params.get("distance") or 0.01)
        resolution = int(params.get("resolution") or 16)
        features = []
        for feature in fc.get("features") or []:
            geom = feature.get("geometry")
            if geom is None:
                features.append(feature)
                continue
            buffered = shape(geom).buffer(distance, resolution=resolution)
            features.append(
                {
                    "type": "Feature",
                    "properties": dict(feature.get("properties") or {}),
                    "geometry": json.loads(json.dumps(buffered.__geo_interface__)),
                }
            )
        out = {"type": "FeatureCollection", "features": features, "crs": fc.get("crs")}
        return {
            "data": out,
            "metadata": {
                "feature_count": len(features),
                "distance": distance,
                "operation": "buffer",
            },
        }


class FilterTransformer(Base4GIxNode):
    node_type = "attribute_filter"
    category = "Transformer"
    is_spatial = False
    label = "Filtre attributaire"
    description = "Filtre les entités selon une égalité attributaire."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Filtre attributaire",
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "title": "Champ",
                    "default": "category",
                },
                "operator": {
                    "type": "string",
                    "title": "Opérateur",
                    "enum": ["eq", "neq", "contains", "gt", "lt"],
                    "default": "eq",
                },
                "value": {
                    "type": "string",
                    "title": "Valeur",
                },
            },
            "required": ["field", "value"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        field = params.get("field")
        operator = params.get("operator") or "eq"
        value = params.get("value")
        if fc is None:
            raise ValueError("Aucune donnée en entrée pour le filtre.")

        def match(props: Dict[str, Any]) -> bool:
            current = props.get(field)
            if operator == "eq":
                return str(current) == str(value)
            if operator == "neq":
                return str(current) != str(value)
            if operator == "contains":
                return str(value).lower() in str(current).lower()
            try:
                left = float(current)
                right = float(value)
            except (TypeError, ValueError):
                return False
            if operator == "gt":
                return left > right
            if operator == "lt":
                return left < right
            return False

        features = [
            f
            for f in fc.get("features") or []
            if match(f.get("properties") or {})
        ]
        out = {"type": "FeatureCollection", "features": features, "crs": fc.get("crs")}
        return {
            "data": out,
            "metadata": {
                "feature_count": len(features),
                "filtered_from": len(fc.get("features") or []),
                "field": field,
                "operator": operator,
                "value": value,
            },
        }


class AttributeMapperTransformer(Base4GIxNode):
    node_type = "attribute_mapper"
    category = "Transformer"
    is_spatial = False
    label = "Mapping attributaire"
    description = "Renomme ou conserve un sous-ensemble de champs."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Mapping attributaire",
            "type": "object",
            "properties": {
                "mapping": {
                    "type": "string",
                    "title": "Mapping de colonnes",
                    "format": "mapping",
                    "description": "Ancien nom → nouveau nom",
                    "default": '{"name": "nom"}',
                },
                "keep_unmapped": {
                    "type": "boolean",
                    "title": "Conserver les champs non mappés",
                    "default": True,
                },
            },
            "required": ["mapping"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        if fc is None:
            raise ValueError("Aucune donnée en entrée pour le mapping.")
        raw_mapping = params.get("mapping") or "{}"
        mapping = json.loads(raw_mapping) if isinstance(raw_mapping, str) else raw_mapping
        keep = params.get("keep_unmapped", True)
        features = []
        for feature in fc.get("features") or []:
            props = dict(feature.get("properties") or {})
            new_props: Dict[str, Any] = {}
            if keep:
                new_props.update(props)
            for old, new in mapping.items():
                if old in props:
                    new_props[new] = props[old]
                    if keep and old != new:
                        new_props.pop(old, None)
            features.append(
                {
                    "type": "Feature",
                    "properties": new_props,
                    "geometry": feature.get("geometry"),
                }
            )
        out = {"type": "FeatureCollection", "features": features, "crs": fc.get("crs")}
        return {
            "data": out,
            "metadata": {
                "feature_count": len(features),
                "mapping": mapping,
            },
        }
