"""Normalisation CRS pour GeoPandas, Fiona et PROJ."""

from __future__ import annotations

from typing import Any, Optional

from pyproj import CRS


def crs_from_geojson_dict(crs: Any) -> Optional[str]:
    """Extrait un nom d'autorité depuis un CRS GeoJSON (`type: name`, etc.)."""
    if not isinstance(crs, dict):
        return None
    props = crs.get("properties") or {}
    name = props.get("name") or crs.get("name")
    if name:
        text = str(name).strip()
        return text or None
    return None


def normalize_crs(crs: Any, default: str = "EPSG:4326") -> str:
    """
    Retourne une chaîne CRS plate (ex. ``EPSG:4326``) utilisable par
    ``GeoDataFrame.set_crs`` / ``to_file``, jamais un dict GeoJSON.
    """
    if crs is None:
        return default

    if not isinstance(crs, (str, dict)) and hasattr(crs, "to_authority"):
        try:
            auth = crs.to_authority()
            if auth:
                return f"{auth[0]}:{auth[1]}"
        except Exception:  # noqa: BLE001
            pass

    if isinstance(crs, dict):
        extracted = crs_from_geojson_dict(crs)
        if not extracted:
            return default
        crs = extracted

    text = str(crs).strip()
    if not text:
        return default

    try:
        parsed = CRS.from_user_input(text)
        auth = parsed.to_authority()
        if auth:
            return f"{auth[0]}:{auth[1]}"
        return parsed.to_wkt()
    except Exception:  # noqa: BLE001
        if text.upper().startswith("EPSG:"):
            return text
        return default
