from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from shapely.geometry import mapping
from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.sqlsafe import qualified_identifier, simple_identifier
from app.nodes.base import Base4GIxNode


class PostGISReader(Base4GIxNode):
    node_type = "postgis_reader"
    category = "Reader"
    is_spatial = True
    label = "PostGIS Reader"
    description = "Lit une table ou une requête SQL spatiale depuis PostGIS."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "PostGIS Reader",
            "description": "Source spatiale PostGIS (table ou SQL).",
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "title": "Table",
                    "description": "Schéma.table (ex. samples.poi)",
                    "default": "samples.poi",
                },
                "geom_column": {
                    "type": "string",
                    "title": "Colonne géométrie",
                    "default": "geom",
                },
                "sql": {
                    "type": "string",
                    "title": "Requête SQL (optionnelle)",
                    "format": "sql",
                    "description": "Si renseignée, remplace la lecture de table.",
                },
                "limit": {
                    "type": "integer",
                    "title": "Limite",
                    "default": 500,
                    "minimum": 1,
                    "maximum": 10000,
                },
            },
            "required": [],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        geom_column = simple_identifier(params.get("geom_column") or "geom")
        limit = int(params.get("limit") or 500)
        sql = (params.get("sql") or "").strip()
        table = qualified_identifier((params.get("table") or "samples.poi").strip())

        if sql:
            wrapped = (
                f"SELECT src.*, ST_AsGeoJSON(src.{geom_column}) AS _geojson "
                f"FROM ({sql}) AS src LIMIT {limit}"
            )
        else:
            wrapped = (
                f"SELECT t.*, ST_AsGeoJSON(t.{geom_column}) AS _geojson "
                f"FROM {table} AS t LIMIT {limit}"
            )

        engine = create_engine(settings.sqlalchemy_url)
        features: List[Dict[str, Any]] = []
        columns: List[str] = []
        with engine.connect() as conn:
            try:
                result = conn.execute(text(wrapped))
            except Exception:
                if not sql:
                    raise
                result = conn.execute(text(sql))
            columns = list(result.keys())
            for row in result.mappings():
                record = dict(row)
                geojson_raw = record.pop("_geojson", None)
                geom_raw = record.pop(geom_column, None)
                geometry: Optional[Dict[str, Any]] = None
                if geojson_raw:
                    geometry = json.loads(geojson_raw) if isinstance(geojson_raw, str) else geojson_raw
                elif geom_raw is not None and hasattr(geom_raw, "__geo_interface__"):
                    geometry = mapping(geom_raw)
                properties = {
                    k: v for k, v in record.items() if k not in {geom_column, "_geojson"}
                }
                features.append(
                    {
                        "type": "Feature",
                        "properties": properties,
                        "geometry": geometry,
                    }
                )

        data = {"type": "FeatureCollection", "features": features}
        return {
            "data": data,
            "metadata": {
                "source": "postgis",
                "table": table,
                "sql": sql or None,
                "feature_count": len(features),
                "columns": [c for c in columns if c not in {geom_column, "_geojson"}],
                "crs": "EPSG:4326",
            },
        }
