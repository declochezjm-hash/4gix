from __future__ import annotations

import json
from typing import Any, Dict, List

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from app.core.paths import resolve_workspace_path
from app.core.readers.shapefile import shapefile_read_outputs
from app.nodes.base import Base4GIxNode


class DxfReaderNode(Base4GIxNode):
    node_type = "dxf_reader"
    category = "Reader"
    is_spatial = True
    label = "CAD / DXF Reader"
    description = "Import AutoCAD geometry features"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "DXF CAD Reader",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier DXF",
                    "default": "/workspace/samples/sample.dxf",
                    "description": "DXF natif. Un DWG doit être converti en DXF au préalable.",
                },
                "layers": {
                    "type": "string",
                    "title": "Calques (optionnel)",
                    "description": "Liste séparée par des virgules. Vide = tous les calques.",
                },
                "source_crs": {
                    "type": "string",
                    "title": "CRS source",
                    "format": "epsg",
                    "default": "EPSG:4326",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        import ezdxf

        path = resolve_workspace_path(params.get("path"), "/workspace/samples/sample.dxf")
        if not path.exists():
            raise FileNotFoundError(f"Fichier DXF introuvable: {path}")
        if path.suffix.lower() == ".dwg":
            raise ValueError(
                "ezdxf ne lit pas le DWG binaire. Convertissez le fichier en DXF (ODA File Converter)."
            )

        doc = ezdxf.readfile(str(path))
        msp = doc.modelspace()
        layer_filter = {
            item.strip()
            for item in str(params.get("layers") or "").split(",")
            if item.strip()
        }
        source_crs = params.get("source_crs") or "EPSG:4326"
        features: List[Dict[str, Any]] = []

        for entity in msp:
            layer = getattr(entity.dxf, "layer", "0")
            if layer_filter and layer not in layer_filter:
                continue
            geom = _entity_geometry(entity)
            if geom is None:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "layer": layer,
                        "dxf_type": entity.dxftype(),
                        "color": getattr(entity.dxf, "color", None),
                    },
                    "geometry": json.loads(json.dumps(geom.__geo_interface__)),
                }
            )

        gdf = gpd.GeoDataFrame.from_features(features, crs=source_crs)
        if str(source_crs).upper() != "EPSG:4326" and not gdf.empty:
            gdf = gdf.to_crs("EPSG:4326")
        if len(gdf):
            geojson, map_geojson, spatial_meta = shapefile_read_outputs(gdf)
        else:
            geojson = {"type": "FeatureCollection", "features": features}
            map_geojson = geojson
            spatial_meta = {"feature_count": 0, "bbox": None}
        meta = {
            "kind": "cad",
            "source": "dxf",
            "path": str(path),
            "feature_count": len(features),
            "layers": sorted({f["properties"]["layer"] for f in features}),
            "crs": "EPSG:4326",
        }
        meta.update(spatial_meta)
        return {
            "data": geojson,
            "map_geojson": map_geojson,
            "metadata": meta,
        }


def _entity_geometry(entity):
    dxftype = entity.dxftype()
    try:
        if dxftype in {"LINE"}:
            return LineString(
                [
                    (entity.dxf.start.x, entity.dxf.start.y),
                    (entity.dxf.end.x, entity.dxf.end.y),
                ]
            )
        if dxftype in {"LWPOLYLINE", "POLYLINE"}:
            points = []
            if hasattr(entity, "get_points"):
                points = [(p[0], p[1]) for p in entity.get_points("xy")]
            elif hasattr(entity, "vertices"):
                points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            if len(points) < 2:
                return None
            closed = bool(getattr(entity, "closed", False) or getattr(entity, "is_closed", False))
            if closed and points[0] != points[-1]:
                points.append(points[0])
            if closed and len(points) >= 4:
                return Polygon(points)
            return LineString(points)
        if dxftype == "POINT":
            loc = entity.dxf.location
            return Point(loc.x, loc.y)
        if dxftype == "CIRCLE":
            center = entity.dxf.center
            return Point(center.x, center.y).buffer(float(entity.dxf.radius))
        if dxftype == "HATCH":
            paths = []
            for path in entity.paths:
                coords = []
                if hasattr(path, "vertices"):
                    coords = [(v[0], v[1]) for v in path.vertices]
                if len(coords) >= 3:
                    if coords[0] != coords[-1]:
                        coords.append(coords[0])
                    paths.append(Polygon(coords))
            if paths:
                return paths[0]
    except Exception:  # noqa: BLE001
        return None
    return None
