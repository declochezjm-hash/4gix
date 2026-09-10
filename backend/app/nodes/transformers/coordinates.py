from __future__ import annotations

import json
from typing import Any, Dict

import geopandas as gpd
from pyproj import CRS

from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data
from app.nodes.fme_features import ports_payload


class ReprojectorNode(Base4GIxNode):
    node_type = "reprojector"
    category = "Transformer"
    is_spatial = True
    label = "Reprojector"
    description = "Reprojection dynamique PROJ/PyProj avec détection des unités (degrés ↔ mètres)."
    fme_group = "Coordinate Systems"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Reprojector",
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
                    "description": "Lambert-93, UTM, Web Mercator…",
                },
            },
            "required": ["target_crs"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data)
        if fc is None:
            raise ValueError("Aucune géométrie en entrée pour Reprojector.")
        source_crs = params.get("source_crs") or "EPSG:4326"
        target_crs = params.get("target_crs") or "EPSG:2154"
        src = CRS.from_user_input(source_crs)
        dst = CRS.from_user_input(target_crs)
        gdf = gpd.GeoDataFrame.from_features(fc.get("features") or [], crs=source_crs)
        gdf = gdf.to_crs(target_crs)
        out = json.loads(gdf.to_json())
        out["crs"] = {"type": "name", "properties": {"name": target_crs}}
        payload = ports_payload(
            {"output": out.get("features") or []},
            feature_type=self.node_type,
            crs=target_crs,
            extra_meta={
                "source_crs": source_crs,
                "target_crs": target_crs,
                "source_units": _axis_unit(src),
                "target_units": _axis_unit(dst),
                "unit_conversion": f"{_axis_unit(src)} → {_axis_unit(dst)}",
            },
        )
        payload["data"]["crs"] = out["crs"]
        return payload


def _axis_unit(crs: CRS) -> str:
    try:
        unit = (crs.axis_info[0].unit_name or "").lower()
    except Exception:  # noqa: BLE001
        return "unknown"
    if "degree" in unit:
        return "degrees"
    if "metre" in unit or "meter" in unit:
        return "metres"
    return unit or "unknown"
