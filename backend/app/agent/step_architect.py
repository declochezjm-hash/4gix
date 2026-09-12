"""Auto-architecte séquentiel : plan global + une mutation canvas par étape."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.agent.composer import (
    detect_export_writer,
    parse_attribute_filter,
    parse_target_crs,
    _wants_analysis,
    _wants_reproject,
)
from app.agent.tools import (
    execute_tool,
    find_node,
    graph_edges,
    graph_nodes,
    inspect_input_schema,
    node_type_of,
)

ARCHITECT_STEP_OFFSET_X = 300.0
ARCHITECT_BRANCH_OFFSET_Y = 40.0

STEP_ARCHITECT_SYSTEM_PROMPT = """
Tu es le planificateur Step Architect. Tu décomposes l'objectif global en
étapes canvas DISTINCTES (une mutation = un nœud).

Règles impératives :
- Si l'objectif contient plusieurs verbes/actions distincts
  (lire/analyser + reprojeter/filtrer + exporter/sauvegarder/générer),
  tu DOIS créer une séquence de 2 à 3 étapes distinctes.
- Ne fusionne jamais et n'ignore jamais les étapes d'inspection ni d'export
  (shapefile_writer / vector_writer).
- is_complete vaut False tant qu'il reste des actions de l'objectif à réaliser.

Dictionnaire d'intention → nœud :
- Analyse / inspection / lecture du CSV → attribute_manager
- Reprojection CC43 (ou « en CC43 ») → reprojector, target_crs=EPSG:3943
- Reprojection générique / EPSG:xxxx → reprojector
- Génère un SHP / Shapefile / shp → shapefile_writer
- Export GeoJSON / GeoPackage → geojson_writer / gpkg_writer

Exemple : « Analyse le csv, fait une reprojection en CC43, et genere un shp »
1. Inspection/Analyse du CSV (attribute_manager)
2. Reprojection dans le système de coordonnées (reprojector, EPSG:3943)
3. Écriture/Export Shapefile (shapefile_writer)
""".strip()

_AREA_FILTER_RE = re.compile(
    r"(?:surface|parcelles?|superficie|aires?)"
    r"[^\d]{0,40}?(?:>|≥|>=|supérieur(?:e)?s?\s+à|superieur(?:e)?s?\s+à)\s*"
    r"(\d+(?:[.,]\d+)?)\s*(?:m\s*²|m2|m\^2)?",
    re.IGNORECASE,
)


@dataclass
class StepDefinition:
    kind: str
    summary: str
    node_type: str
    config: Dict[str, Any]


def _node_position(node: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not node:
        return {"x": 120.0, "y": 180.0}
    pos = node.get("position") if isinstance(node.get("position"), dict) else {}
    return {"x": float(pos.get("x") or 120), "y": float(pos.get("y") or 180)}


def _parse_area_threshold(objective: str) -> Optional[float]:
    text = objective or ""
    match = _AREA_FILTER_RE.search(text)
    if match:
        return float(match.group(1).replace(",", "."))
    generic = re.search(
        r"(?:>|≥|>=)\s*(\d+(?:[.,]\d+)?)\s*(?:m\s*²|m2|m\^2)",
        text,
        re.IGNORECASE,
    )
    if generic:
        return float(generic.group(1).replace(",", "."))
    return None


def _wants_area_filter(objective: str) -> bool:
    text = (objective or "").lower()
    return bool(_parse_area_threshold(objective)) or any(
        token in text
        for token in ("surface", "parcelle", "superficie", "m²", "m2", "hectare")
    )


def _area_filter_code(threshold: float, target_crs: str) -> str:
    return (
        "# Filtre surfacique généré par Step Architect\n"
        f"work = gdf.to_crs('{target_crs}') if str(gdf.crs) != '{target_crs}' else gdf.copy()\n"
        "work['_area_m2'] = work.geometry.area\n"
        f"return work[work['_area_m2'] > {threshold}]\n"
    )


def _inspect_step() -> StepDefinition:
    return StepDefinition(
        kind="inspect",
        summary="Inspection et analyse des données d'entrée",
        node_type="attribute_manager",
        config={"operations": "[]"},
    )


def build_step_plan(
    global_objective: str,
    inspect: Dict[str, Any],
) -> List[StepDefinition]:
    """Construit la liste ordonnée d'étapes à partir de l'objectif global.

    Suit STEP_ARCHITECT_SYSTEM_PROMPT : plusieurs verbes => 2 à 3 nœuds distincts.
    """
    objective = global_objective or ""
    steps: List[StepDefinition] = []
    source_crs = str(inspect.get("crs") or "EPSG:4326")
    if not source_crs.upper().startswith("EPSG"):
        source_crs = "EPSG:4326"

    wants_inspect = _wants_analysis(objective)
    target_crs = parse_target_crs(objective)
    needs_reproject = _wants_reproject(objective) or (
        target_crs.upper() != source_crs.upper() and "2154" in objective
    )
    filter_spec = parse_attribute_filter(objective)
    area_threshold = _parse_area_threshold(objective)
    wants_attr_filter = bool(filter_spec)
    wants_area = (not wants_attr_filter) and _wants_area_filter(objective) and area_threshold is not None
    writer_type = detect_export_writer(objective)

    if wants_inspect:
        steps.append(_inspect_step())

    if needs_reproject:
        steps.append(
            StepDefinition(
                kind="reproject",
                summary=f"Reprojection vers {target_crs}",
                node_type="reprojector",
                config={
                    "source_crs": source_crs,
                    "target_crs": target_crs,
                },
            )
        )

    if wants_attr_filter and filter_spec:
        steps.append(
            StepDefinition(
                kind="attribute_filter",
                summary=(
                    f"Filtrage attributaire : {filter_spec['field']} "
                    f"{filter_spec['operator']} {filter_spec['value']}"
                ),
                node_type="attribute_filter",
                config={
                    "field": filter_spec["field"],
                    "operator": filter_spec["operator"],
                    "value": filter_spec["value"],
                },
            )
        )
    elif wants_area and area_threshold is not None:
        metric_crs = target_crs if needs_reproject else (
            target_crs if "2154" in target_crs else "EPSG:2154"
        )
        steps.append(
            StepDefinition(
                kind="area_filter",
                summary=f"Filtrage des entités dont la surface > {area_threshold:g} m²",
                node_type="python_caller",
                config={
                    "language": "python",
                    "code": _area_filter_code(area_threshold, metric_crs),
                },
            )
        )

    if writer_type:
        label = {
            "geojson_writer": "GeoJSON",
            "gpkg_writer": "GeoPackage",
            "shapefile_writer": "Shapefile",
            "csv_writer": "CSV",
        }.get(writer_type, writer_type)
        steps.append(
            StepDefinition(
                kind="export",
                summary=f"Export {label}",
                node_type=writer_type,
                config={},
            )
        )

    distinct_actions = sum(
        (
            wants_inspect,
            needs_reproject,
            wants_attr_filter or wants_area,
            bool(writer_type),
        )
    )
    if distinct_actions >= 2 and len(steps) < 2:
        if needs_reproject and not any(step.kind == "reproject" for step in steps):
            steps.append(
                StepDefinition(
                    kind="reproject",
                    summary=f"Reprojection vers {target_crs}",
                    node_type="reprojector",
                    config={"source_crs": source_crs, "target_crs": target_crs},
                )
            )
        if writer_type and not any(step.kind == "export" for step in steps):
            steps.append(
                StepDefinition(
                    kind="export",
                    summary="Export Shapefile",
                    node_type=writer_type,
                    config={},
                )
            )

    if not steps:
        steps.append(_inspect_step())

    return steps


def format_plan_labels(steps: List[StepDefinition]) -> List[str]:
    return [f"{index + 1}. {step.summary}" for index, step in enumerate(steps)]


def _is_auto_architect_node(node: Optional[Dict[str, Any]]) -> bool:
    if not node:
        return False
    return node_type_of(node).lower() == "auto_architect_agent"


def _find_auto_architect_id(
    graph: Dict[str, Any],
    source_node_id: str,
) -> Optional[str]:
    """Préfère l'agent branché sur la source, sinon le premier Auto-Architect du graphe."""
    nodes = graph_nodes(graph)
    by_id = {str(item.get("id")): item for item in nodes}
    for edge in graph_edges(graph):
        if str(edge.get("source")) != str(source_node_id):
            continue
        target = by_id.get(str(edge.get("target")))
        if _is_auto_architect_node(target) and target.get("id"):
            return str(target.get("id"))
    for node in nodes:
        if _is_auto_architect_node(node) and node.get("id"):
            return str(node.get("id"))
    return None


def _anchor_node_id(
    source_node_id: str,
    previous_steps: List[Dict[str, Any]],
    step_index: int,
    *,
    graph: Optional[Dict[str, Any]] = None,
    layout_anchor_node_id: Optional[str] = None,
) -> str:
    """Nœud dont la sortie alimente l'étape courante (chaîne A → B → C).

    Étape 1 : Auto-Architect (ancre visuelle), pas le reader CSV amont.
    """
    if step_index > 0:
        if step_index - 1 < len(previous_steps):
            prev = previous_steps[step_index - 1]
            if isinstance(prev, dict) and prev.get("node_id"):
                return str(prev["node_id"])
        if previous_steps:
            last = previous_steps[-1]
            if isinstance(last, dict) and last.get("node_id"):
                return str(last["node_id"])
        if layout_anchor_node_id:
            return str(layout_anchor_node_id)
        return source_node_id

    if layout_anchor_node_id:
        return str(layout_anchor_node_id)
    if graph:
        architect_id = _find_auto_architect_id(graph, source_node_id)
        if architect_id:
            return architect_id
    return source_node_id


def _layout_next_position(
    graph: Dict[str, Any],
    anchor_id: str,
    branch_index: int = 0,
) -> Dict[str, float]:
    """Place le prochain nœud à droite de l'ancre, même Y (ligne horizontale)."""
    del branch_index  # séquence linéaire : pas de décalage vertical
    anchor_node = find_node(graph, anchor_id)
    if not anchor_node:
        for node in graph_nodes(graph):
            if str(node.get("id")) == str(anchor_id):
                anchor_node = node
                break
    origin = _node_position(anchor_node)
    return {
        "x": origin["x"] + ARCHITECT_STEP_OFFSET_X,
        "y": origin["y"],
    }


def plan_step_architect(
    *,
    global_objective: str,
    current_step_index: int,
    previous_steps: List[Dict[str, Any]],
    current_graph: Dict[str, Any],
    source_node_id: str,
    layout_anchor_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    graph = current_graph or {"nodes": [], "edges": [], "snapshots": {}}
    inspect = inspect_input_schema(source_node_id, graph)
    steps = build_step_plan(global_objective, inspect)
    global_plan = format_plan_labels(steps)

    if current_step_index < 0:
        current_step_index = 0
    if current_step_index >= len(steps):
        return {
            "ok": True,
            "global_objective": global_objective,
            "global_plan": global_plan,
            "current_step_index": current_step_index,
            "total_steps": len(steps),
            "inspect": inspect,
            "is_complete": True,
            "step_summary": None,
            "next_step_hint": None,
            "proposed_node": None,
            "proposed_edge": None,
        }

    step = steps[current_step_index]
    anchor_id = _anchor_node_id(
        source_node_id,
        previous_steps,
        current_step_index,
        graph=graph,
        layout_anchor_node_id=layout_anchor_node_id,
    )
    position = _layout_next_position(graph, anchor_id, branch_index=0)

    proposed_node = execute_tool(
        "create_canvas_node",
        {
            "node_type": step.node_type,
            "position": position,
            "config": step.config,
        },
        graph,
    )
    proposed_edge = execute_tool(
        "connect_nodes",
        {
            "from_node_id": anchor_id,
            "from_port": "output",
            "to_node_id": proposed_node["id"],
            "to_port": "input",
        },
        graph,
    )

    next_hint: Optional[str] = None
    if current_step_index + 1 < len(steps):
        next_hint = global_plan[current_step_index + 1]

    return {
        "ok": True,
        "global_objective": global_objective,
        "global_plan": global_plan,
        "current_step_index": current_step_index,
        "total_steps": len(steps),
        "inspect": inspect,
        "is_complete": False,
        "step_kind": step.kind,
        "step_summary": step.summary,
        "next_step_hint": next_hint,
        "proposed_node": proposed_node,
        "proposed_edge": proposed_edge,
        "anchor_node_id": anchor_id,
    }
