from __future__ import annotations

from typing import Any, Dict

from app.core.paths import resolve_workspace_path
from app.core.raster_preview import describe_raster
from app.nodes.base import Base4GIxNode


class GeoTiffRasterReaderNode(Base4GIxNode):
    node_type = "geotiff_raster_reader"
    category = "Reader"
    is_spatial = True
    label = "GeoTIFF Raster Reader"
    description = "Lit un GeoTIFF (orthophoto, satellite, MNT) et produit une prévisualisation PNG."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "GeoTIFF Raster Reader",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier GeoTIFF",
                    "default": "/workspace/samples/sample_dem.tif",
                },
                "band": {
                    "type": "integer",
                    "title": "Bande",
                    "default": 1,
                    "minimum": 1,
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        import rasterio

        path = resolve_workspace_path(params.get("path"), "/workspace/samples/sample_dem.tif")
        if not path.exists():
            raise FileNotFoundError(f"GeoTIFF introuvable: {path}")
        band = int(params.get("band") or 1)
        with rasterio.open(path) as src:
            if band > src.count:
                raise ValueError(f"Bande {band} absente (count={src.count}).")
            data = src.read(band, masked=True)
            stats = {
                "min": float(data.min()) if data.count() else None,
                "max": float(data.max()) if data.count() else None,
                "mean": float(data.mean()) if data.count() else None,
            }
        payload = describe_raster(path, extra={"band": band, "stats": stats})
        return {
            "data": payload,
            "metadata": {
                "kind": "raster",
                "source": "geotiff",
                "path": str(path),
                "crs": payload.get("crs"),
                "width": payload.get("width"),
                "height": payload.get("height"),
                "stats": stats,
            },
        }
