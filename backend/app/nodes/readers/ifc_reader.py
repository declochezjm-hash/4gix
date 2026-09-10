from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from app.core.paths import resolve_workspace_path
from app.nodes.base import Base4GIxNode


IFC_CLASSES = [
    "IfcBuildingElement",
    "IfcWall",
    "IfcSlab",
    "IfcWindow",
    "IfcDoor",
    "IfcColumn",
    "IfcBeam",
    "IfcPipeSegment",
    "IfcBuilding",
    "IfcSpace",
]


def _site_origin(model) -> Tuple[float, float, float]:
    for site in model.by_type("IfcSite"):
        lat = getattr(site, "RefLatitude", None)
        lon = getattr(site, "RefLongitude", None)
        elev = getattr(site, "RefElevation", None) or 0.0
        if lat and lon:
            def _dms(values) -> float:
                vals = list(values)
                sign = 1 if vals[0] >= 0 else -1
                deg = abs(float(vals[0]))
                minutes = float(vals[1]) if len(vals) > 1 else 0.0
                seconds = float(vals[2]) if len(vals) > 2 else 0.0
                return sign * (deg + minutes / 60.0 + seconds / 3600.0)

            return _dms(lon), _dms(lat), float(elev)
    return 2.3522, 48.8566, 0.0


def _local_xyz(element) -> Optional[Tuple[float, float, float]]:
    try:
        from ifcopenshell.util.placement import get_local_placement

        placement = getattr(element, "ObjectPlacement", None)
        if placement is None:
            return None
        matrix = get_local_placement(placement)
        return float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3])
    except Exception:  # noqa: BLE001
        return None


def _footprint_geom(element) -> Optional[Polygon]:
    try:
        import ifcopenshell.geom

        settings = ifcopenshell.geom.settings()
        try:
            settings.set(settings.USE_WORLD_COORDS, True)
        except Exception:  # noqa: BLE001
            pass
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = list(shape.geometry.verts)
        if len(verts) < 9:
            return None
        points = [(verts[i], verts[i + 1]) for i in range(0, len(verts), 3)]
        hull = unary_union([Point(x, y).buffer(0.05) for x, y in points]).convex_hull
        if hull.geom_type == "Polygon" and hull.area > 0:
            return hull
    except Exception:  # noqa: BLE001
        return None
    return None


def _psets(element) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    try:
        import ifcopenshell.util.element as element_util

        for pset_name, values in (element_util.get_psets(element) or {}).items():
            if not isinstance(values, dict):
                continue
            for key, value in values.items():
                if key == "id":
                    continue
                props[f"{pset_name}.{key}" if pset_name else key] = value
    except Exception:  # noqa: BLE001
        pass
    return props


def _to_wgs84(x: float, y: float, origin_lon: float, origin_lat: float) -> Tuple[float, float]:
    # Approximation locale : mètres → degrés autour de l'origine du site.
    lon = origin_lon + (x / (111_320.0 * max(0.2, abs(__import__("math").cos(__import__("math").radians(origin_lat))))))
    lat = origin_lat + (y / 110_540.0)
    return lon, lat


class IfcBimReaderNode(Base4GIxNode):
    node_type = "ifc_bim_reader"
    category = "Reader"
    is_spatial = True
    label = "IFC BIM Reader"
    description = "Parse un fichier IFC (murs, dalles, réseaux) et expose empreintes / centroïdes GeoJSON."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "IFC BIM Reader",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier IFC",
                    "default": "/workspace/samples/sample.ifc",
                    "description": "Chemin local workspace.",
                },
                "ifc_class": {
                    "type": "string",
                    "title": "Classe IFC",
                    "enum": ["ALL"] + IFC_CLASSES,
                    "enumNames": ["Toutes les classes"] + IFC_CLASSES,
                    "default": "IfcBuildingElement",
                },
                "representation": {
                    "type": "string",
                    "title": "Géométrie",
                    "enum": ["footprint", "centroid"],
                    "enumNames": ["Empreinte 2D", "Centroïde"],
                    "default": "footprint",
                },
                "limit": {
                    "type": "integer",
                    "title": "Limite d'entités",
                    "default": 400,
                    "minimum": 1,
                    "maximum": 5000,
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        import ifcopenshell

        path = resolve_workspace_path(params.get("path"), "/workspace/samples/sample.ifc")
        if not path.exists():
            raise FileNotFoundError(f"Fichier IFC introuvable: {path}")

        model = ifcopenshell.open(str(path))
        origin_lon, origin_lat, origin_z = _site_origin(model)
        ifc_class = params.get("ifc_class") or "IfcBuildingElement"
        representation = params.get("representation") or "footprint"
        limit = int(params.get("limit") or 400)

        if ifc_class == "ALL":
            entities = list(model.by_type("IfcProduct"))
        else:
            entities = list(model.by_type(ifc_class))
            if ifc_class == "IfcBuildingElement":
                extra = []
                for subtype in ("IfcWall", "IfcSlab", "IfcWindow", "IfcDoor", "IfcColumn", "IfcBeam"):
                    extra.extend(model.by_type(subtype))
                seen = {e.id() for e in entities}
                entities.extend(e for e in extra if e.id() not in seen)

        features: List[Dict[str, Any]] = []
        for element in entities[:limit]:
            xyz = _local_xyz(element) or (0.0, 0.0, 0.0)
            lon, lat = _to_wgs84(xyz[0], xyz[1], origin_lon, origin_lat)
            geom = None
            if representation == "footprint":
                footprint = _footprint_geom(element)
                if footprint is not None:
                    mapped = [
                        list(_to_wgs84(x, y, origin_lon, origin_lat))
                        for x, y in footprint.exterior.coords
                    ]
                    geom = {"type": "Polygon", "coordinates": [mapped]}
            if geom is None:
                geom = {"type": "Point", "coordinates": [lon, lat]}

            height = float(xyz[2] or 0.0)
            props = {
                "GlobalId": getattr(element, "GlobalId", None),
                "Name": getattr(element, "Name", None),
                "ifc_class": element.is_a(),
                "Elevation": height,
                "height": max(height, 3.0),
                **_psets(element),
            }
            features.append({"type": "Feature", "properties": props, "geometry": geom})

        gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
        geojson = json.loads(gdf.to_json()) if len(gdf) else {"type": "FeatureCollection", "features": features}
        return {
            "data": geojson,
            "metadata": {
                "kind": "bim",
                "source": "ifc",
                "path": str(path),
                "ifc_class": ifc_class,
                "feature_count": len(features),
                "crs": "EPSG:4326",
                "origin": {"lon": origin_lon, "lat": origin_lat, "elevation": origin_z},
                "schema": model.schema,
            },
        }
