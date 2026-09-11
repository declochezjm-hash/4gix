"""Schémas OpenAI / Pydantic des tools agentiques du canvas ETL."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _node_registry():
    try:
        from app.nodes import NODE_REGISTRY, get_node_class

        return NODE_REGISTRY, get_node_class
    except Exception:  # noqa: BLE001
        return {}, None


class InspectInputSchemaArgs(BaseModel):
    """Inspecte le schéma d'entrée (colonnes, types, géométrie, CRS EPSG) d'un nœud."""

    node_id: str = Field(..., description="Identifiant du nœud à inspecter.")


class CreateCanvasNodeArgs(BaseModel):
    """Crée un nœud sur le canvas (python_caller, reproject, attribute_filter, writer_gpkg, …)."""

    node_type: str = Field(
        ...,
        description="Type de nœud (ex: python_caller, reproject, attribute_filter, writer_gpkg, gpkg_writer).",
    )
    position: Dict[str, float] = Field(
        default_factory=lambda: {"x": 0.0, "y": 0.0},
        description="Coordonnées X/Y du nœud sur le canvas.",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Paramètres de configuration du nœud (params).",
    )


class ConnectNodesArgs(BaseModel):
    """Crée une liaison (Edge) entre deux nœuds du canvas."""

    from_node_id: str = Field(..., description="Nœud source.")
    from_port: str = Field(default="output", description="Port de sortie (handle).")
    to_node_id: str = Field(..., description="Nœud cible.")
    to_port: str = Field(default="input", description="Port d'entrée (handle).")


class UpdateNodeCodeArgs(BaseModel):
    """Injecte ou met à jour le script Python / SQL dans un nœud de transformation."""

    node_id: str = Field(..., description="Identifiant du nœud (python_caller / code_node).")
    code: str = Field(..., description="Script à injecter.")
    language: str = Field(default="python", description="Langage du script: python ou sql.")


TOOL_MODELS: Dict[str, type[BaseModel]] = {
    "inspect_input_schema": InspectInputSchemaArgs,
    "create_canvas_node": CreateCanvasNodeArgs,
    "connect_nodes": ConnectNodesArgs,
    "update_node_code": UpdateNodeCodeArgs,
}

_TOOL_DESCRIPTIONS: Dict[str, str] = {
    "inspect_input_schema": InspectInputSchemaArgs.__doc__ or "",
    "create_canvas_node": CreateCanvasNodeArgs.__doc__ or "",
    "connect_nodes": ConnectNodesArgs.__doc__ or "",
    "update_node_code": UpdateNodeCodeArgs.__doc__ or "",
}

# Alias canvas → type registre 4GIx
NODE_TYPE_ALIASES: Dict[str, str] = {
    "writer_gpkg": "file_writer",
    "gpkg_writer": "file_writer",
    "geojson_writer": "file_writer",
    "csv_writer": "file_writer",
    "shapefile_writer": "file_writer",
    "code": "python_caller",
    "code_node": "python_caller",
    "filter": "attribute_filter",
    "reproject": "reproject",
}


def _openai_parameters(model: type[BaseModel]) -> Dict[str, Any]:
    schema = model.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)
    return schema


def openai_tool_schema(name: str) -> Dict[str, Any]:
    model = TOOL_MODELS[name]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": " ".join((_TOOL_DESCRIPTIONS.get(name) or "").split()),
            "parameters": _openai_parameters(model),
        },
    }


AGENT_OPENAI_TOOLS: List[Dict[str, Any]] = [
    openai_tool_schema(name) for name in TOOL_MODELS
]


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def graph_nodes(graph: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not graph:
        return []
    return list(graph.get("nodes") or [])


def graph_edges(graph: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not graph:
        return []
    return list(graph.get("edges") or [])


def find_node(graph: Optional[Dict[str, Any]], node_id: str) -> Optional[Dict[str, Any]]:
    for node in graph_nodes(graph):
        if str(node.get("id")) == str(node_id):
            return node
    return None


def node_type_of(node: Dict[str, Any]) -> str:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    return str(
        data.get("nodeType")
        or data.get("node_type")
        or node.get("nodeType")
        or node.get("node_type")
        or node.get("type")
        or ""
    )


def resolve_node_type(node_type: str) -> str:
    key = (node_type or "").strip()
    aliased = NODE_TYPE_ALIASES.get(key, key)
    if aliased == "etl":
        return key
    registry, _ = _node_registry()
    if aliased in registry or aliased in {"python_caller", "code_node"}:
        return aliased
    return aliased


def writer_config_for(requested_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(config or {})
    requested = (requested_type or "").lower()
    if requested in {"writer_gpkg", "gpkg_writer"}:
        params.setdefault("driver", "GPKG")
        params.setdefault("path", "/workspace/output.gpkg")
    elif requested in {"geojson_writer"}:
        params.setdefault("driver", "GeoJSON")
        params.setdefault("path", "/workspace/output.geojson")
    elif requested in {"csv_writer"}:
        params.setdefault("driver", "CSV")
        params.setdefault("path", "/workspace/output.csv")
    elif requested in {"shapefile_writer"}:
        params.setdefault("driver", "ESRI Shapefile")
        params.setdefault("path", "/workspace/output.shp")
    return params


def _infer_field_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _as_feature_collection(payload: Any, depth: int = 0) -> Dict[str, Any]:
    """Remonte un GeoJSON FeatureCollection depuis un snapshot imbriqué (items / data / preview)."""
    if depth > 6 or not isinstance(payload, dict):
        return {}
    if payload.get("type") == "FeatureCollection" and isinstance(
        payload.get("features"), list
    ):
        return payload
    for key in (
        "geojson",
        "data",
        "output_snapshot",
        "input_snapshot",
        "preview",
        "items",
        "output",
        "input",
    ):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = _as_feature_collection(nested, depth + 1)
            if found.get("features"):
                return found
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            sample = nested[0]
            if "geometry" in sample or "properties" in sample:
                return {"type": "FeatureCollection", "features": nested}
    return {}


def _crs_from_payload(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    crs = payload.get("crs")
    if isinstance(crs, str) and crs.strip():
        return crs
    if isinstance(crs, dict):
        props = crs.get("properties") or {}
        name = props.get("name") or crs.get("name")
        if name:
            return str(name)
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    for key in ("crs", "epsg", "srid"):
        if meta.get(key):
            return str(meta[key])
    return None


def inspect_input_schema(
    node_id: str,
    graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Inspecte colonnes, types, géométrie et CRS EPSG d'un nœud du graphe courant."""
    node = find_node(graph, node_id)
    if node is None:
        return {
            "ok": False,
            "node_id": node_id,
            "error": f"Nœud introuvable: {node_id}",
            "fields": [],
            "geometry": None,
            "crs": None,
        }

    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    ntype = node_type_of(node)
    snapshots = graph.get("snapshots") if isinstance(graph, dict) else {}
    snap: Dict[str, Any] = {}
    if isinstance(snapshots, dict):
        snap = snapshots.get(node_id) or snapshots.get(str(node_id)) or {}
    if not isinstance(snap, dict):
        snap = {}
    preview = (
        data.get("outputSnapshot")
        or data.get("inputSnapshot")
        or data.get("preview")
        or data.get("output_snapshot")
        or data.get("input_snapshot")
        or snap.get("output_snapshot")
        or snap.get("input_snapshot")
        or snap.get("preview")
        or {}
    )
    if not isinstance(preview, dict):
        preview = {}
    geojson = _as_feature_collection(preview)
    if not geojson.get("features"):
        geojson = _as_feature_collection(data)
    if not geojson.get("features"):
        for other in graph_nodes(graph):
            other_data = other.get("data") if isinstance(other.get("data"), dict) else {}
            candidate = _as_feature_collection(
                other_data.get("inputSnapshot")
                or other_data.get("outputSnapshot")
                or other_data
            )
            if candidate.get("features"):
                geojson = candidate
                preview = other_data if isinstance(other_data, dict) else preview
                break

    features = geojson.get("features") if isinstance(geojson, dict) else None
    fields: List[Dict[str, Any]] = []
    geom_types: List[str] = []
    if isinstance(features, list) and features:
        sample = features[0] if isinstance(features[0], dict) else {}
        props = sample.get("properties") if isinstance(sample.get("properties"), dict) else {}
        for name, value in props.items():
            fields.append({"name": name, "type": _infer_field_type(value)})
        for feat in features[:50]:
            if not isinstance(feat, dict):
                continue
            geom = feat.get("geometry")
            if isinstance(geom, dict) and geom.get("type"):
                geom_types.append(str(geom["type"]))

    schema = data.get("schema") if isinstance(data.get("schema"), dict) else {}
    crs = _crs_from_payload(geojson) or _crs_from_payload(preview) or data.get("crs")
    geometry = None
    if geom_types:
        geometry = sorted(set(geom_types))[0]
    else:
        registry, get_node_class = _node_registry()
        if ntype.endswith("_reader") or ntype in registry:
            try:
                if get_node_class is not None:
                    cls = get_node_class(ntype)
                    geometry = "geometry" if getattr(cls, "is_spatial", False) else None
            except KeyError:
                geometry = None

    return {
        "ok": True,
        "node_id": node_id,
        "node_type": ntype,
        "label": data.get("label") or node.get("id"),
        "fields": fields,
        "field_count": len(fields),
        "geometry": geometry,
        "geometry_types": sorted(set(geom_types)),
        "crs": crs,
        "params": data.get("params") or {},
        "schema_title": schema.get("title"),
        "feature_count": len(features) if isinstance(features, list) else None,
    }


def create_canvas_node(
    node_type: str,
    position: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Construit un nœud canvas React Flow.
    Retourne l'identifiant du nœud créé (le payload complet est dans le dernier résultat).
    """
    payload = create_canvas_node_payload(node_type, position or {}, config or {})
    return str(payload["id"])


_LAST_CREATED_NODE: Dict[str, Any] = {}


def create_canvas_node_payload(
    node_type: str,
    position: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    requested = (node_type or "").strip()
    resolved = resolve_node_type(requested)
    params = writer_config_for(requested, dict(config or {}))
    pos = position or {}
    x = float(pos.get("x") or 0)
    y = float(pos.get("y") or 0)

    label = requested
    category = "Transformer"
    is_spatial = False
    input_handles = ["input"]
    output_handles = ["output"]
    schema: Dict[str, Any] = {}
    _, get_node_class = _node_registry()
    try:
        if get_node_class is not None:
            cls = get_node_class(resolved)
            entry = cls.catalog_entry()
            label = entry.get("label") or resolved
            category = entry.get("category") or category
            is_spatial = bool(entry.get("is_spatial"))
            input_handles = list(entry.get("input_handles") or input_handles)
            output_handles = list(entry.get("output_handles") or output_handles)
            schema = entry.get("schema") or {}
    except KeyError:
        label = requested or resolved

    if requested in {"writer_gpkg", "gpkg_writer"}:
        label = "GeoPackage Writer"
        category = "Writer"
        is_spatial = True
    elif requested == "geojson_writer":
        label = "GeoJSON Writer"
        category = "Writer"
        is_spatial = True
    elif requested == "attribute_filter":
        label = "Filter by Attribute"

    node_id = _short_id(requested or resolved or "node")
    node = {
        "id": node_id,
        "type": "etl",
        "position": {"x": x, "y": y},
        "data": {
            "label": label,
            "nodeType": resolved,
            "requestedNodeType": requested,
            "category": category,
            "isSpatial": is_spatial,
            "params": params,
            "schema": schema,
            "status": "idle",
            "inputHandles": input_handles,
            "outputHandles": output_handles,
            "notes": "",
            "disabled": False,
        },
    }
    _LAST_CREATED_NODE.clear()
    _LAST_CREATED_NODE.update(node)
    return node


def connect_nodes(
    from_node_id: str,
    from_port: str,
    to_node_id: str,
    to_port: str,
) -> Dict[str, Any]:
    """Crée une arête React Flow entre deux nœuds."""
    edge_id = f"e-{from_node_id}-{to_node_id}-{uuid.uuid4().hex[:6]}"
    return {
        "id": edge_id,
        "source": from_node_id,
        "sourceHandle": from_port or "output",
        "target": to_node_id,
        "targetHandle": to_port or "input",
    }


def update_node_code(
    node_id: str,
    code: str,
    language: str,
    graph: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Retourne le patch params (code + language) à appliquer au nœud."""
    lang = (language or "python").lower()
    if lang not in {"python", "sql"}:
        lang = "python"
    previous = ""
    node = find_node(graph, node_id)
    if node:
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        previous = str(params.get("code") or "")
    return {
        "ok": True,
        "node_id": node_id,
        "language": lang,
        "code": code,
        "previous_code": previous,
        "params_patch": {"code": code, "language": lang},
    }


def execute_tool(
    name: str,
    arguments: Dict[str, Any],
    graph: Optional[Dict[str, Any]] = None,
) -> Any:
    """Exécute un tool agentique et retourne le payload canvas."""
    if name == "inspect_input_schema":
        args = InspectInputSchemaArgs.model_validate(arguments)
        return inspect_input_schema(args.node_id, graph)
    if name == "create_canvas_node":
        args = CreateCanvasNodeArgs.model_validate(arguments)
        return create_canvas_node_payload(args.node_type, args.position, args.config)
    if name == "connect_nodes":
        args = ConnectNodesArgs.model_validate(arguments)
        return connect_nodes(args.from_node_id, args.from_port, args.to_node_id, args.to_port)
    if name == "update_node_code":
        args = UpdateNodeCodeArgs.model_validate(arguments)
        return update_node_code(args.node_id, args.code, args.language, graph)
    raise ValueError(f"Tool inconnu: {name}")


def tool_call_summary(name: str, arguments: Dict[str, Any]) -> str:
    """Résumé compact pour la vérification (create_node / connect)."""
    if name == "create_canvas_node":
        ntype = arguments.get("node_type") or ""
        return f"create_node({ntype})"
    if name == "connect_nodes":
        src = arguments.get("from_node_id") or ""
        dst = arguments.get("to_node_id") or ""
        return f"connect({src} -> {dst})"
    if name == "inspect_input_schema":
        return f"inspect_input_schema({arguments.get('node_id')})"
    if name == "update_node_code":
        return f"update_node_code({arguments.get('node_id')})"
    return name
