from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


class Base4GIxNode(ABC):
    """Contrat d'interface de tous les nœuds ETL / SIG 4GIx."""

    node_type: str
    category: str  # Reader, Transformer, Writer
    is_spatial: bool = False
    label: str = ""
    description: str = ""
    input_handles: List[str] = ["input"]
    output_handles: List[str] = ["output"]
    fme_group: str = ""

    @classmethod
    @abstractmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Retourne la structure du formulaire pour la fenêtre Config du Frontend."""
        pass

    @abstractmethod
    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        inputs: Données issues des nœuds parents
        params: Paramètres de configuration du nœud
        returns: Output structuré pour le nœud suivant + snapshot UI
        """
        pass

    @classmethod
    def catalog_entry(cls) -> Dict[str, Any]:
        schema = cls.get_schema()
        return {
            "node_type": cls.node_type,
            "category": cls.category,
            "is_spatial": cls.is_spatial,
            "label": cls.label or schema.get("title") or cls.node_type,
            "description": cls.description or schema.get("description") or "",
            "schema": schema,
            "input_handles": list(cls.input_handles or ["input"]),
            "output_handles": list(cls.output_handles or ["output"]),
            "fme_group": cls.fme_group or "",
        }


@dataclass
class NodeSnapshot:
    """Représentation UI d'un nœud après exécution."""

    node_id: str
    node_type: str
    status: str = "success"
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    preview: Optional[Dict[str, Any]] = None
    input_snapshot: Optional[Any] = None
    output_snapshot: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "preview": self.preview,
            "input_snapshot": self.input_snapshot,
            "output_snapshot": self.output_snapshot,
            "error": self.error,
        }


def _as_feature_collection(payload: Any) -> Optional[Dict[str, Any]]:
    if payload is None:
        return None
    if isinstance(payload, dict):
        if payload.get("type") in {"RasterDataset", "Raster"}:
            return None
        if payload.get("kind") == "raster":
            return None
        if payload.get("type") == "FeatureCollection":
            return payload
        if payload.get("type") == "Feature":
            return {"type": "FeatureCollection", "features": [payload]}
        if "features" in payload and isinstance(payload["features"], list):
            return {
                "type": "FeatureCollection",
                "features": payload["features"],
                "crs": payload.get("crs"),
            }
        if "geometry" in payload and payload.get("geometry") is not None:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": payload.get("properties") or {},
                        "geometry": payload["geometry"],
                    }
                ],
            }
        if "data" in payload:
            return _as_feature_collection(payload["data"])
        if "geojson" in payload:
            return _as_feature_collection(payload["geojson"])
    if isinstance(payload, BaseGeometry):
        return {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {}, "geometry": mapping(payload)}
            ],
        }
    if isinstance(payload, list):
        features = []
        for item in payload:
            fc = _as_feature_collection(item)
            if fc:
                features.extend(fc.get("features") or [])
        if features:
            return {"type": "FeatureCollection", "features": features}
    return None


def _geometry_types(fc: Dict[str, Any]) -> List[str]:
    types: List[str] = []
    for feature in fc.get("features") or []:
        geom = (feature or {}).get("geometry") or {}
        gtype = geom.get("type")
        if gtype and gtype not in types:
            types.append(gtype)
    return types


def _preview_limit(fc: Dict[str, Any], limit: int = 50) -> Dict[str, Any]:
    features = fc.get("features") or []
    return {
        "type": "FeatureCollection",
        "crs": fc.get("crs"),
        "features": features[:limit],
        "truncated": len(features) > limit,
        "total": len(features),
    }


def extract_json_preview(payload: Any, limit: int = 50) -> Any:
    if payload is None:
        return None
    if isinstance(payload, dict):
        if "records" in payload and isinstance(payload["records"], list):
            records = payload["records"]
            return {
                "records": records[:limit],
                "truncated": len(records) > limit,
                "total": len(records),
            }
        keys = [k for k in payload.keys() if k not in {"snapshot"}]
        return {k: payload[k] for k in keys}
    if isinstance(payload, list):
        return {"records": payload[:limit], "total": len(payload), "truncated": len(payload) > limit}
    return payload


def build_snapshot_from_payload(
    node_id: str,
    node_type: str,
    payload: Dict[str, Any],
    duration_ms: float,
    category: str = "",
    is_spatial: bool = False,
) -> Dict[str, Any]:
    from app.core.raster_preview import compact_raster_payload, is_raster_payload

    fc = _as_feature_collection(payload)
    metadata: Dict[str, Any] = {
        "category": category,
        "is_spatial": is_spatial,
    }
    if isinstance(payload, dict):
        metadata.update(payload.get("metadata") or {})

    if is_raster_payload(payload):
        preview = compact_raster_payload(payload)
        return NodeSnapshot(
            node_id=node_id,
            node_type=node_type,
            status="success",
            duration_ms=duration_ms,
            metadata=metadata,
            preview=preview,
            output_snapshot=preview,
        ).to_dict()

    if isinstance(payload, dict) and payload.get("ports"):
        from app.nodes.fme_features import port_previews

        previews = port_previews(payload)
        metadata.setdefault("fme_ports", True)
        primary = previews.get("output") or (fc and _preview_limit(fc))
        return NodeSnapshot(
            node_id=node_id,
            node_type=node_type,
            status="success",
            duration_ms=duration_ms,
            metadata=metadata,
            preview=primary,
            output_snapshot={"ports": previews, "data": payload.get("data")},
        ).to_dict()

    if fc is not None:
        metadata.setdefault("feature_count", len(fc.get("features") or []))
        metadata.setdefault("geometry_types", _geometry_types(fc))
        if fc.get("crs"):
            metadata.setdefault("crs", fc.get("crs"))
        preview: Any = _preview_limit(fc)
    else:
        preview = extract_json_preview(payload.get("data") if isinstance(payload, dict) else payload)
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            metadata.setdefault("record_count", len(payload["data"]))

    output_snapshot = fc if fc is not None else extract_json_preview(
        payload.get("data") if isinstance(payload, dict) else payload
    )
    return NodeSnapshot(
        node_id=node_id,
        node_type=node_type,
        status="success",
        duration_ms=duration_ms,
        metadata=metadata,
        preview=preview,
        output_snapshot=output_snapshot,
    ).to_dict()


def unwrap_handle(raw: Any) -> Any:
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    return raw


def unwrap_input_data(inputs: Dict[str, Any]) -> Any:
    """Récupère le payload métier du premier parent (handle `input` ou unique clé)."""
    if not inputs:
        return None
    raw = inputs.get("input")
    if raw is None and len(inputs) == 1:
        raw = next(iter(inputs.values()))
    return unwrap_handle(raw)


def unwrap_named_input(inputs: Dict[str, Any], handle: str) -> Any:
    if not inputs:
        return None
    if handle in inputs:
        return unwrap_handle(inputs[handle])
    aliases = {
        "input_a": ["a", "left", "input", "request", "base"],
        "input_b": ["b", "right", "supplier", "candidates", "clipper"],
        "clipper": ["mask", "clip", "input_b"],
        "request": ["input", "input_a", "left"],
        "supplier": ["input_b", "right"],
        "base": ["input", "request", "input_a"],
        "candidates": ["supplier", "input_b"],
    }
    for alias in aliases.get(handle, []):
        if alias in inputs:
            return unwrap_handle(inputs[alias])
    return None


def snapshot_payload(data: Any) -> Any:
    from app.core.raster_preview import compact_raster_payload, is_raster_payload

    if isinstance(data, dict) and "data" in data:
        inner = data["data"]
        if is_raster_payload(data) or is_raster_payload(inner):
            return compact_raster_payload(data)
        data = inner
    if is_raster_payload(data):
        return compact_raster_payload(data)
    fc = _as_feature_collection(data)
    if fc is not None:
        return _preview_limit(fc)
    return extract_json_preview(data)


def records_from_geojson(data: Any) -> List[Dict[str, Any]]:
    fc = _as_feature_collection(data)
    if not fc:
        if isinstance(data, list):
            return list(data)
        return []
    rows: List[Dict[str, Any]] = []
    for feature in fc.get("features") or []:
        props = dict(feature.get("properties") or {})
        geom = feature.get("geometry")
        if geom is not None:
            try:
                props["_geometry"] = shape(geom)
            except Exception:  # noqa: BLE001
                props["_geojson"] = geom
        rows.append(props)
    return rows
