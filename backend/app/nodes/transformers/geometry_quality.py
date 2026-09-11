from __future__ import annotations

from typing import Any, Dict

from shapely.ops import transform as shp_transform
from shapely.validation import explain_validity, make_valid

from app.nodes.base import Base4GIxNode
from app.nodes.workflow_features import (
    feature_from_shapely,
    input_features,
    ports_payload,
    shapely_of,
)

try:
    from pyproj import Transformer
except Exception:  # noqa: BLE001
    Transformer = None  # type: ignore[assignment]


def _to_metric(geom, crs: str):
    if Transformer is None or not crs or "4326" not in str(crs):
        return geom, None
    fwd = Transformer.from_crs(crs, "EPSG:2154", always_xy=True)
    back = Transformer.from_crs("EPSG:2154", crs, always_xy=True)
    return shp_transform(fwd.transform, geom), back


class GeometryValidatorNode(Base4GIxNode):
    node_type = "geometry_validator"
    category = "Transformer"
    is_spatial = True
    label = "Validate Geometry"
    description = "Detect and repair invalid shapes"
    output_handles = ["output", "rejected"]
    palette_group = "Geometry & Quality"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "GeometryValidator",
            "type": "object",
            "properties": {
                "repair": {"type": "boolean", "title": "Réparer (make_valid)", "default": True},
                "allow_empty": {"type": "boolean", "title": "Accepter les géométries vides", "default": False},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        repair = params.get("repair", True)
        allow_empty = params.get("allow_empty", False)
        passed, rejected = [], []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            props = dict(feature.get("properties") or {})
            if geom is None:
                if allow_empty:
                    passed.append(feature)
                else:
                    rejected.append(
                        feature_from_shapely(None, props, feature_type=self.node_type, rejection_code="NULL_GEOMETRY")
                    )
                continue
            if geom.is_valid and not geom.is_empty:
                passed.append(feature)
                continue
            if geom.is_empty and not allow_empty:
                rejected.append(
                    feature_from_shapely(geom, props, feature_type=self.node_type, rejection_code="EMPTY_GEOMETRY")
                )
                continue
            if repair:
                try:
                    fixed = make_valid(geom)
                    if hasattr(fixed, "geoms"):
                        fixed = max(fixed.geoms, key=lambda g: g.area if g.geom_type in {"Polygon", "MultiPolygon"} else g.length)
                    if fixed.is_valid and not fixed.is_empty:
                        passed.append(feature_from_shapely(fixed, props, feature_type=self.node_type))
                        continue
                except Exception:  # noqa: BLE001
                    pass
            code = explain_validity(geom) if not geom.is_valid else "UNREPAIRABLE"
            rejected.append(
                feature_from_shapely(geom, {**props, "validity": code}, feature_type=self.node_type, rejection_code=str(code)[:80])
            )
        return ports_payload(
            {"output": passed, "rejected": rejected},
            feature_type=self.node_type,
            extra_meta={"repaired": True},
        )


class GeometryFilterNode(Base4GIxNode):
    node_type = "geometry_filter"
    category = "Transformer"
    is_spatial = True
    label = "GeometryFilter"
    description = "Sépare le flux par type de géométrie (Point, Line, Polygon, MultiPolygon, Null)."
    output_handles = ["point", "linestring", "polygon", "multipolygon", "null"]
    palette_group = "Geometry & Quality"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {"title": "GeometryFilter", "type": "object", "properties": {}}

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        buckets = {name: [] for name in self.output_handles}
        mapping_types = {
            "Point": "point",
            "MultiPoint": "point",
            "LineString": "linestring",
            "MultiLineString": "linestring",
            "Polygon": "polygon",
            "MultiPolygon": "multipolygon",
        }
        for feature in input_features(inputs):
            gtype = (feature.get("geometry") or {}).get("type") if feature.get("geometry") else None
            buckets[mapping_types.get(str(gtype), "null")].append(feature)
        return ports_payload(buckets, feature_type=self.node_type, primary="polygon")


class SnapperNode(Base4GIxNode):
    node_type = "snapper"
    category = "Transformer"
    is_spatial = True
    label = "Snapper"
    description = "Calage des sommets sur une grille de tolérance (mètres)."
    palette_group = "Geometry & Quality"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Snapper",
            "type": "object",
            "properties": {
                "tolerance": {"type": "number", "title": "Tolérance (m)", "format": "slider", "default": 1.0, "minimum": 0.01, "maximum": 50},
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        tolerance = float(params.get("tolerance") or 1.0)
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                out.append(feature)
                continue
            metric, back = _to_metric(geom, "EPSG:4326")
            snapped = metric.set_precision(grid_size=max(tolerance, 0.01)) if hasattr(metric, "set_precision") else metric
            if back:
                snapped = shp_transform(back.transform, snapped)
            out.append(feature_from_shapely(snapped, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)


class OrientorNode(Base4GIxNode):
    node_type = "orientor"
    category = "Transformer"
    is_spatial = True
    label = "Orientor"
    description = "Uniformise l'orientation des anneaux (horaire / anti-horaire)."
    palette_group = "Geometry & Quality"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Orientor",
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "title": "Orientation",
                    "enum": ["ccw", "cw"],
                    "enumNames": ["Anti-horaire (CCW)", "Horaire (CW)"],
                    "default": "ccw",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        from shapely.geometry.polygon import orient

        sign = 1.0 if (params.get("direction") or "ccw") == "ccw" else -1.0
        out = []
        for feature in input_features(inputs):
            geom = shapely_of(feature)
            if geom is None:
                out.append(feature)
                continue
            if geom.geom_type in {"Polygon", "MultiPolygon"}:
                if geom.geom_type == "Polygon":
                    geom = orient(geom, sign=sign)
                else:
                    geom = type(geom)([orient(p, sign=sign) for p in geom.geoms])
            out.append(feature_from_shapely(geom, feature.get("properties"), feature_type=self.node_type))
        return ports_payload({"output": out}, feature_type=self.node_type)
