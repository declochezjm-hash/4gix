"""Plan de correctif après échec d'exécution (géométrie / CRS)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agent.geometry_healing import (
    coordinate_pair,
    enrich_inspect_geometry_flags,
    explain_geometry_error,
    geometry_builder_python_code,
    geometry_heal_step_config,
    inspect_has_geometry,
    is_geometry_related_error,
    is_spatial_writer,
    resolve_spatial_export_writer,
)
from app.agent.tools import (
    execute_tool,
    find_node,
    graph_edges,
    inspect_input_schema,
    node_type_of,
)


def _upstream_parent(graph: Dict[str, Any], node_id: str) -> Optional[str]:
    for edge in graph_edges(graph):
        if str(edge.get("target")) == str(node_id):
            return str(edge.get("source"))
    return None


def plan_execution_heal(
    *,
    error_message: str,
    failed_node_id: str,
    current_graph: Dict[str, Any],
    global_objective: str,
    source_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    graph = current_graph or {"nodes": [], "edges": []}
    failed = find_node(graph, failed_node_id)
    if not failed:
        return {
            "ok": False,
            "error": f"Nœud en échec introuvable : {failed_node_id}",
        }
    failed_type = node_type_of(failed)
    if not is_geometry_related_error(error_message) and not is_spatial_writer(
        failed_type
    ):
        return {
            "ok": False,
            "error": "Cet échec ne correspond pas à un problème de géométrie/CRS connu.",
        }

    parent_id = _upstream_parent(graph, failed_node_id) or source_node_id
    if not parent_id:
        return {"ok": False, "error": "Impossible de déterminer le nœud amont."}

    inspect = enrich_inspect_geometry_flags(inspect_input_schema(parent_id, graph))
    explanation = explain_geometry_error(error_message)
    corrective_steps: List[Dict[str, Any]] = []

    heal_cfg = geometry_heal_step_config(inspect)
    if heal_cfg and not inspect_has_geometry(inspect):
        corrective_steps.append(
            {
                "node_type": "python_caller",
                "summary": "Création de géométrie (colonnes X/Y ou lat/lon)",
                "config": heal_cfg,
                "insert_before_node_id": failed_node_id,
                "connect_from_node_id": parent_id,
            }
        )
    else:
        resolved, _extra, _msgs = resolve_spatial_export_writer(failed_type, inspect)
        if resolved == "csv_writer" and failed_type != "csv_writer":
            corrective_steps.append(
                {
                    "node_type": "csv_writer",
                    "summary": "Repli export CSV (données sans géométrie)",
                    "config": {},
                    "replace_node_id": failed_node_id,
                }
            )

    pair = coordinate_pair(inspect)
    if pair and not corrective_steps:
        x_col, y_col = pair
        corrective_steps.append(
            {
                "node_type": "python_caller",
                "summary": "Création de géométrie à partir des coordonnées",
                "config": {
                    "language": "python",
                    "code": geometry_builder_python_code(x_col, y_col),
                },
                "insert_before_node_id": failed_node_id,
                "connect_from_node_id": parent_id,
            }
        )

    if not corrective_steps:
        return {
            "ok": False,
            "explanation": explanation,
            "error": "Aucun correctif automatique applicable.",
            "inspect": inspect,
        }

    proposed_node = None
    proposed_edge = None
    first = corrective_steps[0]
    if first.get("insert_before_node_id") and first.get("connect_from_node_id"):
        failed_node = find_node(graph, failed_node_id) or {}
        pos = failed_node.get("position") if isinstance(failed_node.get("position"), dict) else {}
        x = float(pos.get("x") or 0) - 280
        y = float(pos.get("y") or 0)
        proposed_node = execute_tool(
            "create_canvas_node",
            {
                "node_type": first.get("node_type"),
                "position": {"x": x, "y": y},
                "config": first.get("config") or {},
            },
            graph,
        )
        proposed_edge = execute_tool(
            "connect_nodes",
            {
                "from_node_id": first["connect_from_node_id"],
                "from_port": "output",
                "to_node_id": proposed_node["id"],
                "to_port": "input",
            },
            graph,
        )

    return {
        "ok": True,
        "explanation": explanation,
        "global_objective": global_objective,
        "failed_node_id": failed_node_id,
        "corrective_steps": corrective_steps,
        "inspect": inspect,
        "proposed_node": proposed_node,
        "proposed_edge": proposed_edge,
        "heal_followup_edge": {
            "from_node_id": proposed_node["id"] if proposed_node else None,
            "to_node_id": failed_node_id,
        }
        if proposed_node
        else None,
        "auto_apply_hint": (
            "Insérez le nœud de géométrie entre le filtre et l'exporteur, "
            "ou basculez l'export en CSV."
        ),
    }
