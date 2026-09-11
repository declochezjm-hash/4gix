"""Lecture KML / KMZ (Google Earth)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import geopandas as gpd

from app.core.readers.shapefile import shapefile_read_outputs


def read_kml_file(path: Path, *, layer: Optional[str] = None) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Fichier KML/KMZ introuvable: {path}")

    kwargs: Dict[str, Any] = {}
    if layer:
        kwargs["layer"] = layer

    gdf = gpd.read_file(path, **kwargs)
    native, map_geojson, meta = shapefile_read_outputs(gdf)
    meta.update(
        {
            "source": "kml",
            "path": str(path),
            "format": path.suffix.lower().lstrip(".") or "kml",
        },
    )
    return {
        "data": native,
        "map_geojson": map_geojson,
        "metadata": meta,
    }
