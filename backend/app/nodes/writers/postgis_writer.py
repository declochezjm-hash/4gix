from __future__ import annotations

import json
from typing import Any, Dict

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.sqlsafe import qualified_identifier, simple_identifier
from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data


class PostGISWriter(Base4GIxNode):
    node_type = "postgis_writer"
    category = "Writer"
    is_spatial = True
    label = "PostGIS Writer"
    description = "Écrit une FeatureCollection dans une table PostGIS."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "PostGIS Writer",
            "type": "object",
            "properties": {
                "schema_name": {
                    "type": "string",
                    "title": "Schéma",
                    "default": "gix_output",
                },
                "table": {
                    "type": "string",
                    "title": "Table",
                    "default": "output_layer",
                },
                "geom_column": {
                    "type": "string",
                    "title": "Colonne géométrie",
                    "default": "geom",
                },
                "if_exists": {
                    "type": "string",
                    "title": "Si la table existe",
                    "enum": ["replace", "append"],
                    "default": "replace",
                },
            },
            "required": ["table"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        if fc is None:
            raise ValueError(
                "Aucune géométrie à écrire dans PostGIS. "
                "Reliez un Reader ou un Transform en amont de ce writer "
                "et vérifiez que le flux contient des entités spatiales."
            )

        schema_name = simple_identifier(params.get("schema_name") or "gix_output")
        table = simple_identifier(params.get("table") or "output_layer")
        geom_column = simple_identifier(params.get("geom_column") or "geom")
        if_exists = params.get("if_exists") or "replace"
        qualified = qualified_identifier(f"{schema_name}.{table}")

        engine = create_engine(settings.sqlalchemy_url)
        features = fc.get("features") or []
        with engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
            if if_exists == "replace":
                conn.execute(text(f"DROP TABLE IF EXISTS {qualified}"))
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {qualified} (
                        id SERIAL PRIMARY KEY,
                        properties JSONB,
                        {geom_column} geometry(Geometry, 4326)
                    )
                    """
                )
            )
            for feature in features:
                props = json.dumps(feature.get("properties") or {})
                geom = json.dumps(feature.get("geometry")) if feature.get("geometry") else None
                if geom:
                    conn.execute(
                        text(
                            f"""
                            INSERT INTO {qualified} (properties, {geom_column})
                            VALUES (
                                CAST(:props AS jsonb),
                                ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326)
                            )
                            """
                        ),
                        {"props": props, "geom": geom},
                    )
                else:
                    conn.execute(
                        text(
                            f"INSERT INTO {qualified} (properties) VALUES (CAST(:props AS jsonb))"
                        ),
                        {"props": props},
                    )

        return {
            "data": fc,
            "metadata": {
                "written": len(features),
                "table": qualified,
                "if_exists": if_exists,
            },
        }
