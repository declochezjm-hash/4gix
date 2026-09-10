from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from shapely.geometry import mapping, shape

from app.core.paths import workspace_subdir
from app.core.raster_preview import describe_raster, is_raster_payload
from app.nodes.base import (
    Base4GIxNode,
    _as_feature_collection,
    unwrap_named_input,
)


class RasterClipperNode(Base4GIxNode):
    node_type = "raster_clipper"
    category = "Transformer"
    is_spatial = True
    label = "Raster Clipper"
    description = "Découpe un GeoTIFF (Input A) par une géométrie vectorielle (Input B)."
    input_handles: List[str] = ["input_a", "input_b"]

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Raster Clipper",
            "type": "object",
            "properties": {
                "all_touched": {
                    "type": "boolean",
                    "title": "Inclure les pixels touchés",
                    "default": True,
                },
                "crop": {
                    "type": "boolean",
                    "title": "Recadrer l'étendue",
                    "default": True,
                },
            },
            "required": [],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        import rasterio
        from rasterio.mask import mask

        raster_data = unwrap_named_input(inputs, "input_a")
        vector_data = unwrap_named_input(inputs, "input_b")
        raster_path = _raster_path(raster_data)
        fc = _as_feature_collection(vector_data)
        if not raster_path:
            raise ValueError("Input A doit être un raster GeoTIFF (nœud GeoTIFF Reader).")
        if fc is None or not fc.get("features"):
            raise ValueError("Input B doit contenir une géométrie vectorielle (polygone).")

        geoms = []
        for feature in fc["features"]:
            geom = feature.get("geometry")
            if geom:
                geoms.append(shape(geom))
        if not geoms:
            raise ValueError("Aucune géométrie valide dans Input B.")

        crop = params.get("crop", True)
        all_touched = params.get("all_touched", True)
        out_path = workspace_subdir("cache") / f"clip_{uuid4().hex}.tif"
        with rasterio.open(raster_path) as src:
            geojson_geoms = [mapping(g) for g in geoms]
            out_image, out_transform = mask(src, geojson_geoms, crop=crop, all_touched=all_touched)
            profile = src.profile.copy()
            profile.update(
                {
                    "height": out_image.shape[1],
                    "width": out_image.shape[2],
                    "transform": out_transform,
                }
            )
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(out_image)

        payload = describe_raster(out_path, extra={"clipped_from": str(raster_path)})
        return {
            "data": payload,
            "metadata": {
                "kind": "raster",
                "operation": "clip",
                "path": str(out_path),
                "source": str(raster_path),
                "crs": payload.get("crs"),
            },
        }


class ZonalStatisticsNode(Base4GIxNode):
    node_type = "zonal_statistics"
    category = "Transformer"
    is_spatial = True
    label = "Zonal Statistics"
    description = "Calcule min / max / moyenne d'un MNT raster sur des polygones vectoriels."
    input_handles: List[str] = ["input_a", "input_b"]

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Zonal Statistics",
            "type": "object",
            "properties": {
                "stats": {
                    "type": "string",
                    "title": "Statistiques",
                    "default": "min,max,mean,count",
                    "description": "Liste séparée par des virgules.",
                },
                "raster_is_a": {
                    "type": "boolean",
                    "title": "Raster sur Input A (sinon Input B)",
                    "default": True,
                },
            },
            "required": [],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        from rasterstats import zonal_stats

        raster_is_a = params.get("raster_is_a", True)
        raster_data = unwrap_named_input(inputs, "input_a" if raster_is_a else "input_b")
        vector_data = unwrap_named_input(inputs, "input_b" if raster_is_a else "input_a")
        raster_path = _raster_path(raster_data)
        fc = _as_feature_collection(vector_data)
        if not raster_path:
            raise ValueError("Un des flux doit être un GeoTIFF (MNT / raster).")
        if fc is None or not fc.get("features"):
            raise ValueError("Un des flux doit être une couche vectorielle.")

        stats_list = [s.strip() for s in str(params.get("stats") or "min,max,mean,count").split(",") if s.strip()]
        geoms = [feature.get("geometry") for feature in fc["features"] if feature.get("geometry")]
        computed = zonal_stats(geoms, raster_path, stats=stats_list, geojson_out=False)
        features = []
        for feature, stats in zip(fc["features"], computed):
            props = dict(feature.get("properties") or {})
            for key, value in (stats or {}).items():
                props[f"z_{key}"] = None if value is None else float(value) if isinstance(value, (int, float)) else value
            features.append(
                {
                    "type": "Feature",
                    "properties": props,
                    "geometry": feature.get("geometry"),
                }
            )
        out = {"type": "FeatureCollection", "features": features, "crs": fc.get("crs")}
        return {
            "data": out,
            "metadata": {
                "kind": "vector",
                "operation": "zonal_statistics",
                "raster": str(raster_path),
                "feature_count": len(features),
                "stats": stats_list,
            },
        }


def _raster_path(data: Any) -> str | None:
    if isinstance(data, dict):
        if data.get("path") and (is_raster_payload(data) or data.get("type") == "RasterDataset"):
            return str(data["path"])
        if data.get("data") and isinstance(data["data"], dict) and data["data"].get("path"):
            return str(data["data"]["path"])
        if data.get("path") and str(data["path"]).lower().endswith((".tif", ".tiff")):
            return str(data["path"])
    if isinstance(data, str) and data.lower().endswith((".tif", ".tiff")):
        path = Path(data)
        return str(path) if path.exists() else None
    return None
