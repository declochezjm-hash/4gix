"""Endpoint Direct Chat Processor — transformation LLM sans nœuds intermédiaires."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.direct_processor import payload_from_gdf, process_direct
from app.agent.tools import _as_feature_collection, graph_edges, graph_nodes, node_type_of
from app.core import persistence
from app.core.transformers.python_caller import features_to_gdf
from app.nodes.base import build_snapshot_from_payload

router = APIRouter(tags=["agent"])


class CurrentGraph(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    snapshots: Dict[str, Any] = Field(default_factory=dict)


class DirectProcessRequest(BaseModel):
    node_id: str = Field(..., description="Nœud cible (snapshot mis à jour en sortie).")
    prompt: str = Field(..., min_length=1)
    sample_limit: int = Field(default=500, ge=1, le=100_000)
    api_key: Optional[str] = Field(
        default=None,
        description="Clé OpenAI (sinon FOURGIX_OPENAI_API_KEY).",
    )
    execution_id: Optional[str] = Field(
        default=None,
        description="Si fourni, persiste le snapshot en base.",
    )
    current_graph: CurrentGraph = Field(
        default_factory=CurrentGraph,
        description="Graphe canvas + snapshots client pour résoudre le parent.",
    )


def _upstream_node_id(graph: Dict[str, Any], node_id: str) -> Optional[str]:
    for edge in graph_edges(graph):
        if str(edge.get("target")) == str(node_id):
            return str(edge.get("source"))
    return None


def _snapshot_blob_from_node_data(data: Dict[str, Any]) -> Dict[str, Any]:
    for key in (
        "outputSnapshot",
        "inputSnapshot",
        "output_snapshot",
        "input_snapshot",
        "preview",
    ):
        val = data.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _resolve_parent_geojson(
    node_id: str,
    graph: Dict[str, Any],
    execution_id: Optional[str],
) -> tuple[Dict[str, Any], str, Dict[str, Any]]:
    """Retourne (geojson_fc, source_node_id, input_snapshot_raw)."""
    parent_id = _upstream_node_id(graph, node_id) or node_id
    snapshots = graph.get("snapshots") if isinstance(graph.get("snapshots"), dict) else {}
    snap = snapshots.get(parent_id) or snapshots.get(str(parent_id)) or {}

    raw_input: Dict[str, Any] = {}
    if isinstance(snap, dict):
        raw_input = (
            snap.get("output_snapshot")
            or snap.get("input_snapshot")
            or snap.get("preview")
            or {}
        )
    if not isinstance(raw_input, dict) or not raw_input:
        for node in graph_nodes(graph):
            if str(node.get("id")) != str(parent_id):
                continue
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            raw_input = _snapshot_blob_from_node_data(data)
            break

    if execution_id and (not raw_input or not _as_feature_collection(raw_input).get("features")):
        persisted = persistence.get_node_snapshot(execution_id, parent_id)
        if persisted:
            raw_input = (
                persisted.get("output_snapshot")
                or persisted.get("input_snapshot")
                or raw_input
            )

    geojson = _as_feature_collection(raw_input)
    if not geojson.get("features"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Aucun snapshot GeoJSON pour le nœud parent « {parent_id} ». "
                "Exécutez le workflow ou fournissez current_graph.snapshots."
            ),
        )
    return geojson, parent_id, raw_input if isinstance(raw_input, dict) else {}


def _node_meta(graph: Dict[str, Any], node_id: str) -> tuple[str, str]:
    for node in graph_nodes(graph):
        if str(node.get("id")) == str(node_id):
            ntype = node_type_of(node)
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            category = str(data.get("category") or "Transformer")
            return ntype, category
    return "direct_processor", "Transformer"


@router.post("/agent/direct-process")
def direct_process(request: DirectProcessRequest) -> Dict[str, Any]:
    graph = request.current_graph.model_dump()
    geojson, parent_id, input_raw = _resolve_parent_geojson(
        request.node_id,
        graph,
        request.execution_id,
    )
    features = list(geojson.get("features") or [])
    gdf = features_to_gdf(features)

    prompt_sample = min(3, request.sample_limit)
    result = process_direct(
        gdf,
        request.prompt,
        request.api_key or "",
        sample_limit=prompt_sample,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": result.get("error"),
                "log": result.get("log"),
            },
        )

    result_gdf = result["gdf"]
    node_type, category = _node_meta(graph, request.node_id)
    payload = payload_from_gdf(
        result_gdf,
        node_type=node_type,
        source_features=features,
    )
    snapshot = build_snapshot_from_payload(
        node_id=request.node_id,
        node_type=node_type,
        payload=payload,
        duration_ms=float(result.get("duration_ms") or 0.0),
        category=category,
        is_spatial=True,
    )

    if request.execution_id:
        persistence.upsert_node_snapshot(
            execution_id=request.execution_id,
            node_id=request.node_id,
            input_snapshot=input_raw,
            output_snapshot=snapshot.get("output_snapshot"),
            execution_time_ms=int(snapshot.get("duration_ms") or 0),
        )

    return {
        "ok": True,
        "node_id": request.node_id,
        "parent_node_id": parent_id,
        "snapshot": snapshot,
        "code": result.get("code"),
        "log": result.get("log"),
        "feature_count_before": result.get("feature_count_before"),
        "feature_count_after": result.get("feature_count_after"),
    }
