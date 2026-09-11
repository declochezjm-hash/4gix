"""Lecture GeoPackage OGC (.gpkg)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd

from app.core.readers.shapefile import shapefile_read_outputs

try:
    import fiona
except ImportError:  # pragma: no cover
    fiona = None


def list_gpkg_layers(path: Path) -> List[str]:
    if fiona is None:
        raise RuntimeError("fiona indisponible pour lister les couches GPKG.")
    if not path.is_file():
        raise FileNotFoundError(f"GeoPackage introuvable: {path}")
    return list(fiona.listlayers(str(path)))


def read_gpkg_file(
    path: Path,
    *,
    layer: Optional[str] = None,
) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"GeoPackage introuvable: {path}")

    layers = list_gpkg_layers(path)
    if not layers:
        raise ValueError("GeoPackage sans couche vectorielle.")

    active = layer or layers[0]
    if active not in layers:
        raise ValueError(
            f"Couche « {active} » absente. Couches : {', '.join(layers)}.",
        )

    gdf = gpd.read_file(path, layer=active)
    native, map_geojson, meta = shapefile_read_outputs(gdf)
    meta.update(
        {
            "source": "gpkg",
            "path": str(path),
            "layer": active,
            "layers": layers,
        },
    )
    return {
        "data": native,
        "map_geojson": map_geojson,
        "metadata": meta,
    }
