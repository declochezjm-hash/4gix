"""Prévisualisation raster PNG (basse résolution, Base64) pour l'inspecteur."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np


def is_raster_payload(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    payload = value.get("data") if "data" in value and isinstance(value.get("data"), dict) else value
    kind = str(payload.get("kind") or payload.get("type") or "").lower()
    return kind in {"raster", "rasterdataset"} or bool(payload.get("preview_png_base64"))


def compact_raster_payload(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    payload = value.get("data") if isinstance(value.get("data"), dict) else value
    if not is_raster_payload(value) and not is_raster_payload(payload):
        return None
    keys = (
        "type",
        "kind",
        "path",
        "crs",
        "bounds",
        "width",
        "height",
        "count",
        "dtype",
        "nodata",
        "preview_png_base64",
        "preview_width",
        "preview_height",
        "stats",
    )
    return {key: payload.get(key) for key in keys if key in payload}


def raster_preview_from_array(
    array: np.ndarray,
    nodata: Optional[float] = None,
    max_size: int = 256,
) -> Tuple[str, int, int]:
    """Encode une bande (ou RGB) en PNG data-URL, rééchantillonnée."""
    from PIL import Image

    data = np.asarray(array)
    if data.ndim == 3:
        # (bands, h, w) -> (h, w, bands)
        if data.shape[0] <= 4 and data.shape[0] < data.shape[1]:
            data = np.transpose(data[:3], (1, 2, 0))
        vis = data[:, :, : min(3, data.shape[2])]
        gray = False
    else:
        vis = data
        gray = True

    vis = vis.astype("float64")
    if nodata is not None:
        vis = np.where(vis == nodata, np.nan, vis)
    finite = vis[np.isfinite(vis)]
    if finite.size == 0:
        scaled = np.zeros(vis.shape[:2] if gray else vis.shape, dtype="uint8")
    else:
        vmin, vmax = np.percentile(finite, (2, 98))
        if vmax <= vmin:
            vmax = vmin + 1.0
        scaled = np.clip((vis - vmin) / (vmax - vmin) * 255.0, 0, 255)
        scaled = np.nan_to_num(scaled, nan=0).astype("uint8")

    if gray:
        image = Image.fromarray(scaled, mode="L")
    elif scaled.ndim == 2:
        image = Image.fromarray(scaled, mode="L")
    else:
        if scaled.shape[2] == 1:
            image = Image.fromarray(scaled[:, :, 0], mode="L")
        else:
            image = Image.fromarray(scaled[:, :, :3], mode="RGB")

    image.thumbnail((max_size, max_size))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}", image.width, image.height


def raster_preview_from_path(path: Path, max_size: int = 256) -> Tuple[str, int, int]:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as src:
        scale = max(src.width, src.height) / float(max_size)
        out_w = max(1, int(src.width / max(scale, 1)))
        out_h = max(1, int(src.height / max(scale, 1)))
        indexes = list(range(1, min(src.count, 3) + 1))
        data = src.read(indexes, out_shape=(len(indexes), out_h, out_w), resampling=Resampling.bilinear)
        if data.shape[0] == 1:
            return raster_preview_from_array(data[0], nodata=src.nodata, max_size=max_size)
        return raster_preview_from_array(data, nodata=src.nodata, max_size=max_size)


def describe_raster(path: Path, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import rasterio

    with rasterio.open(path) as src:
        preview, pw, ph = raster_preview_from_path(path)
        payload: Dict[str, Any] = {
            "type": "RasterDataset",
            "kind": "raster",
            "path": str(path),
            "crs": str(src.crs) if src.crs else None,
            "bounds": list(src.bounds),
            "width": src.width,
            "height": src.height,
            "count": src.count,
            "dtype": str(src.dtypes[0]) if src.dtypes else None,
            "nodata": src.nodata,
            "preview_png_base64": preview,
            "preview_width": pw,
            "preview_height": ph,
        }
        if extra:
            payload.update(extra)
        return payload
