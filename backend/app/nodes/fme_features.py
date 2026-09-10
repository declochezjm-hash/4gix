"""Entités et ports style FME Workbench pour Recflow."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from app.nodes.base import _as_feature_collection, _preview_limit

FME_ATTRS = ("fme_feature_type", "fme_geometry", "fme_crs", "fme_rejection_code")

HANDLE_ALIASES = {
    "output": "output",
    "input": "input",
    "rejected": "rejected",
    "<rejected>": "rejected",
    "passed": "passed",
    "failed": "failed",
    "unique": "unique",
    "duplicate": "duplicate",
    "merged": "merged",
    "unmerged_request": "unmerged_request",
    "unmerged_supplier": "unmerged_supplier",
    "inside": "inside",
    "outside": "outside",
    "point": "point",
    "linestring": "linestring",
    "polygon": "polygon",
    "multipolygon": "multipolygon",
    "null": "null",
    "else": "else",
    "clipper": "clipper",
    "request": "request",
    "supplier": "supplier",
    "base": "base",
    "candidates": "candidates",
    "input_a": "input_a",
    "input_b": "input_b",
    "related": "related",
    "unrelated": "unrelated",
    "output1": "output1",
    "output2": "output2",
    "output3": "output3",
}


def normalize_handle(name: Optional[str], default: str = "output") -> str:
    raw = (name or default).strip()
    key = raw.strip("<>").lower().replace("-", "_").replace(" ", "_")
    return HANDLE_ALIASES.get(key, key)


def empty_fc(crs: Any = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"type": "FeatureCollection", "features": []}
    if crs:
        payload["crs"] = crs if isinstance(crs, dict) else {"type": "name", "properties": {"name": str(crs)}}
    return payload


def features_from_any(data: Any) -> List[Dict[str, Any]]:
    fc = _as_feature_collection(data)
    if not fc:
        return []
    return list(fc.get("features") or [])


def collection(features: Iterable[Dict[str, Any]], crs: Any = "EPSG:4326") -> Dict[str, Any]:
    fc = empty_fc(crs)
    fc["features"] = list(features)
    return fc


def geom_type_of(feature: Dict[str, Any]) -> str:
    geom = (feature or {}).get("geometry")
    if not geom:
        return "Null"
    return str(geom.get("type") or "Null")


def stamp_feature(
    feature: Dict[str, Any],
    *,
    feature_type: str = "",
    crs: str = "EPSG:4326",
    rejection_code: Optional[str] = None,
) -> Dict[str, Any]:
    props = dict(feature.get("properties") or {})
    gtype = geom_type_of(feature)
    props.setdefault("fme_feature_type", feature_type or props.get("fme_feature_type") or "feature")
    props["fme_geometry"] = gtype
    props.setdefault("fme_crs", crs or props.get("fme_crs") or "EPSG:4326")
    if rejection_code:
        props["fme_rejection_code"] = rejection_code
    elif "fme_rejection_code" not in props:
        props["fme_rejection_code"] = None
    return {"type": "Feature", "properties": props, "geometry": feature.get("geometry")}


def stamp_features(
    features: Iterable[Dict[str, Any]],
    *,
    feature_type: str,
    crs: str = "EPSG:4326",
    rejection_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return [
        stamp_feature(f, feature_type=feature_type, crs=crs, rejection_code=rejection_code)
        for f in features
    ]


def shapely_of(feature: Dict[str, Any]) -> Optional[BaseGeometry]:
    geom = feature.get("geometry")
    if not geom:
        return None
    try:
        return shape(geom)
    except Exception:  # noqa: BLE001
        return None


def feature_from_shapely(
    geom: Optional[BaseGeometry],
    properties: Optional[Dict[str, Any]] = None,
    *,
    feature_type: str = "",
    crs: str = "EPSG:4326",
    rejection_code: Optional[str] = None,
) -> Dict[str, Any]:
    geojson_geom = mapping(geom) if geom is not None and not geom.is_empty else None
    return stamp_feature(
        {"type": "Feature", "properties": dict(properties or {}), "geometry": geojson_geom},
        feature_type=feature_type,
        crs=crs,
        rejection_code=rejection_code,
    )


def ports_payload(
    ports: Dict[str, List[Dict[str, Any]]],
    *,
    feature_type: str,
    crs: str = "EPSG:4326",
    extra_meta: Optional[Dict[str, Any]] = None,
    primary: str = "output",
) -> Dict[str, Any]:
    stamped: Dict[str, Dict[str, Any]] = {}
    counts: Dict[str, int] = {}
    for name, feats in ports.items():
        handle = normalize_handle(name, name)
        tagged = stamp_features(feats, feature_type=feature_type, crs=crs)
        stamped[handle] = collection(tagged, crs)
        counts[handle] = len(tagged)
    primary_handle = normalize_handle(primary)
    if primary_handle not in stamped:
        primary_handle = next(iter(stamped), "output")
        if primary_handle not in stamped:
            stamped["output"] = empty_fc(crs)
            primary_handle = "output"
    metadata = {
        "kind": "vector",
        "fme_ports": True,
        "port_counts": counts,
        "crs": crs,
        "feature_count": counts.get(primary_handle, 0),
    }
    if extra_meta:
        metadata.update(extra_meta)
    return {
        "data": stamped[primary_handle],
        "ports": stamped,
        "metadata": metadata,
    }


def extract_port(payload: Any, handle: str) -> Any:
    handle = normalize_handle(handle)
    if payload is None:
        return empty_fc()
    if isinstance(payload, list):
        merged = empty_fc()
        for item in payload:
            fc = extract_port(item, handle)
            merged["features"].extend((fc.get("features") if isinstance(fc, dict) else []) or [])
        return merged
    if not isinstance(payload, dict):
        return payload
    ports = payload.get("ports")
    if isinstance(ports, dict):
        if handle in ports:
            return ports[handle]
        for key, value in ports.items():
            if normalize_handle(key) == handle:
                return value
    if handle in {"output", "input"} and payload.get("data") is not None:
        return payload["data"] if not (isinstance(payload["data"], dict) and payload["data"].get("kind") == "raster") else payload
    if payload.get("type") == "FeatureCollection":
        return payload if handle in {"output", "input"} else empty_fc()
    inner = payload.get("data")
    if isinstance(inner, dict) and inner.get("type") == "FeatureCollection" and handle in {"output", "input"}:
        return inner
    return empty_fc() if handle not in {"output", "input"} else payload


def stamp_payload(payload: Dict[str, Any], feature_type: str, crs: Optional[str] = None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    meta = payload.get("metadata") or {}
    resolved = crs or meta.get("crs") or meta.get("target_crs") or "EPSG:4326"
    if isinstance(resolved, dict):
        resolved = (resolved.get("properties") or {}).get("name") or "EPSG:4326"
    crs = str(resolved)
    ports = payload.get("ports")
    if isinstance(ports, dict):
        new_ports = {}
        for name, value in ports.items():
            feats = stamp_features(features_from_any(value), feature_type=feature_type, crs=crs)
            new_ports[normalize_handle(name, name)] = collection(feats, crs)
        payload = {**payload, "ports": new_ports}
        if "data" in payload:
            payload["data"] = new_ports.get("output") or next(iter(new_ports.values()), payload.get("data"))
        return payload
    fc = _as_feature_collection(payload)
    if fc is not None:
        feats = stamp_features(fc.get("features") or [], feature_type=feature_type, crs=crs)
        data = collection(feats, crs)
        payload = {**payload, "data": data}
        payload.setdefault("ports", {"output": data})
    return payload


def input_features(inputs: Dict[str, Any], handle: str = "input") -> List[Dict[str, Any]]:
    from app.nodes.base import unwrap_input_data, unwrap_named_input

    raw = unwrap_named_input(inputs, handle) if handle != "input" else unwrap_input_data(inputs)
    if raw is None and handle != "input":
        raw = unwrap_input_data(inputs)
    return features_from_any(raw)


def port_previews(payload: Dict[str, Any]) -> Dict[str, Any]:
    ports = payload.get("ports") if isinstance(payload, dict) else None
    if not isinstance(ports, dict):
        return {}
    out: Dict[str, Any] = {}
    for name, value in ports.items():
        fc = _as_feature_collection(value)
        out[name] = _preview_limit(fc) if fc else value
    return out


def vertex_count(geom: Optional[dict]) -> int:
    if not geom:
        return 0
    coords = geom.get("coordinates")
    def walk(item: Any) -> int:
        if not isinstance(item, list) or not item:
            return 0
        if isinstance(item[0], (int, float)):
            return 1
        return sum(walk(child) for child in item)
    return walk(coords)


def bbox_of(geom: Optional[BaseGeometry]) -> Optional[List[float]]:
    if geom is None or geom.is_empty:
        return None
    return list(geom.bounds)
