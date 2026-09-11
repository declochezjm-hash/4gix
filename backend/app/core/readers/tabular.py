"""Lecture tabulaire (CSV / Excel) avec détection de coordonnées."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from app.core.readers.shapefile import MAP_CRS, shapefile_read_outputs

COORD_PAIR_KEYS: List[Tuple[str, str]] = [
    ("longitude", "latitude"),
    ("lon", "lat"),
    ("long", "lat"),
    ("x", "y"),
    ("easting", "northing"),
    ("est", "nord"),
]


def find_xy_columns(columns: List[str]) -> Optional[Tuple[str, str]]:
    lowered = {str(col).strip().lower(): str(col) for col in columns}
    for x_key, y_key in COORD_PAIR_KEYS:
        if x_key in lowered and y_key in lowered:
            return lowered[x_key], lowered[y_key]
    return None


def _points_gdf(df: pd.DataFrame, x_col: str, y_col: str) -> gpd.GeoDataFrame:
    work = df.copy()
    work[x_col] = pd.to_numeric(work[x_col], errors="coerce")
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work.dropna(subset=[x_col, y_col])
    geometry = [Point(xy) for xy in zip(work[x_col], work[y_col], strict=True)]
    attrs = work.drop(columns=[x_col, y_col], errors="ignore")
    gdf = gpd.GeoDataFrame(attrs, geometry=geometry, crs=MAP_CRS)
    return gdf


def tabular_read_outputs(
    df: pd.DataFrame,
    *,
    source: str,
    path: str,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Retourne le payload Reader : table attributs et carte si X/Y détectés."""
    meta: Dict[str, Any] = {
        "source": source,
        "path": path,
        "record_count": int(len(df)),
        "columns": [str(c) for c in df.columns],
    }
    if extra_meta:
        meta.update(extra_meta)

    pair = find_xy_columns(list(df.columns))
    if pair and len(df) > 0:
        x_col, y_col = pair
        gdf = _points_gdf(df, x_col, y_col)
        native, map_geojson, spatial_meta = shapefile_read_outputs(gdf)
        meta.update(spatial_meta)
        meta["coordinate_columns"] = [x_col, y_col]
        return {
            "data": native,
            "map_geojson": map_geojson,
            "metadata": meta,
        }

    records = df.where(pd.notnull(df), None).to_dict(orient="records")
    return {
        "data": records,
        "metadata": meta,
    }
