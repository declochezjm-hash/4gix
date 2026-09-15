"""Auto-architecte séquentiel : plan global + une mutation canvas par étape."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.agent.composer import (
    build_mapping_choice_options,
    detect_export_writer,
    mapping_has_explicit_detail,
    mapping_step_summary,
    needs_mapping_guidance,
    parse_multiple_filter_specs,
    parse_parallel_branch_objectives,
    parse_target_crs,
    resolve_mapping_choice,
    wants_data_cleaning_intent,
    wants_mapping_intent,
    _wants_analysis,
    _wants_reproject,
)
from app.agent.geometry_healing import (
    build_proactive_suggestions,
    coordinate_pair,
    enrich_inspect_geometry_flags,
    geometry_heal_node_type,
    geometry_heal_step_config,
    is_spatial_writer,
    resolve_spatial_export_writer,
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
ARCHITECT_BRANCH_OFFSET_Y = 150.0

STEP_ARCHITECT_SYSTEM_PROMPT = """
Tu es le planificateur Step Architect. Tu décomposes l'objectif global en
étapes canvas DISTINCTES (une mutation = un nœud).

Règles impératives :
- Si l'objectif contient plusieurs verbes/actions distincts
  (lire/analyser + reprojeter/filtrer + exporter/sauvegarder/générer),
  tu DOIS créer une séquence de 2 à 3 étapes distinctes.
- Critères indépendants depuis une même source : branches parallèles distinctes
  (attach_to_source), décalage vertical Y = 150 px par branche.
- Nombre minimal de nœuds = N filtres + M writers ; ne fusionne pas les opérations.
- Avant tout export spatial (.shp, .geojson, .gpkg) depuis données tabulaires,
  insère une étape geometry_heal (python_caller XY) ou repli CSV explicite.
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
    attach_to_source: bool = False
    branch_index: int = 0
    branch_id: int = 0


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


def _expand_geometry_heal_steps(
    steps: List[StepDefinition],
    inspect: Dict[str, Any],
    notices: List[str],
) -> List[StepDefinition]:
    """Insère un python_caller XY avant chaque export spatial si besoin ; repli CSV sinon."""
    enriched = enrich_inspect_geometry_flags(inspect)
    expanded: List[StepDefinition] = []
    for step in steps:
        if step.kind != "export" or not is_spatial_writer(step.node_type):
            expanded.append(step)
            continue
        resolved_type, _extra, msgs = resolve_spatial_export_writer(
            step.node_type, enriched
        )
        notices.extend(msgs)
        heal_cfg = geometry_heal_step_config(enriched)
        heal_type = geometry_heal_node_type(enriched) or "vertex_creator"
        # file_writer reconstruit la géométrie depuis X/Y à l'exécution — pas de nœud dédié.
        if (
            heal_cfg
            and is_spatial_writer(resolved_type)
            and coordinate_pair(enriched) is None
        ):
            expanded.append(
                StepDefinition(
                    kind="geometry_heal",
                    summary="Vertex Creator — colonnes X/Y ou lat/lon",
                    node_type=heal_type,
                    config=heal_cfg,
                    attach_to_source=step.attach_to_source,
                    branch_index=step.branch_index,
                    branch_id=step.branch_id,
                )
            )
        label = step.summary
        if resolved_type == "csv_writer" and step.node_type != "csv_writer":
            label = step.summary.replace("Shapefile", "CSV").replace(
                "GeoJSON", "CSV"
            )
            if "CSV" not in label:
                label = f"{step.summary} (repli CSV)"
        expanded.append(
            StepDefinition(
                kind=step.kind,
                summary=label,
                node_type=resolved_type,
                config=step.config,
                attach_to_source=step.attach_to_source,
                branch_index=step.branch_index,
                branch_id=step.branch_id,
            )
        )
    return expanded


def build_step_plan(
    global_objective: str,
    inspect: Dict[str, Any],
) -> tuple[List[StepDefinition], List[str]]:
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
    schema_fields = inspect.get("fields") if isinstance(inspect.get("fields"), list) else []
    schema_columns = [
        str(item.get("name"))
        for item in schema_fields
        if isinstance(item, dict) and item.get("name")
    ]
    parallel_branches = parse_parallel_branch_objectives(objective, schema_columns)
    if len(parallel_branches) >= 2:
        writer_labels = {
            "geojson_writer": "GeoJSON",
            "gpkg_writer": "GeoPackage",
            "shapefile_writer": "Shapefile",
            "csv_writer": "CSV",
        }
        for branch_id, branch in enumerate(parallel_branches):
            if branch.filter_spec:
                operator = branch.filter_spec.get("operator") or "contains"
                if str(operator).upper() == "CONTAINS":
                    operator = "contains"
                steps.append(
                    StepDefinition(
                        kind="attribute_filter",
                        summary=(
                            f"Branche {branch_id + 1} — filtre "
                            f"{branch.filter_spec['field']} {operator} "
                            f"{branch.filter_spec['value']}"
                        ),
                        node_type="attribute_filter",
                        config={
                            "field": branch.filter_spec["field"],
                            "operator": operator,
                            "value": branch.filter_spec["value"],
                        },
                        attach_to_source=True,
                        branch_index=branch_id,
                        branch_id=branch_id,
                    )
                )
            wt = branch.writer_type
            if wt:
                label = writer_labels.get(wt, wt)
                steps.append(
                    StepDefinition(
                        kind="export",
                        summary=f"Branche {branch_id + 1} — export {label}",
                        node_type=wt,
                        config={},
                        attach_to_source=False,
                        branch_index=branch_id,
                        branch_id=branch_id,
                    )
                )
        if steps:
            notices: List[str] = []
            return _expand_geometry_heal_steps(steps, inspect, notices), notices

    filter_specs = parse_multiple_filter_specs(objective, schema_columns)
    area_threshold = _parse_area_threshold(objective)
    wants_attr_filter = bool(filter_specs)
    wants_area = (not wants_attr_filter) and _wants_area_filter(objective) and area_threshold is not None
    writer_type = detect_export_writer(objective)
    parallel_filters = len(filter_specs) > 1

    if wants_inspect and not parallel_filters:
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

    if wants_attr_filter:
        for index, filter_spec in enumerate(filter_specs):
            operator = filter_spec["operator"]
            if operator.upper() == "CONTAINS":
                operator = "contains"
            steps.append(
                StepDefinition(
                    kind="attribute_filter",
                    summary=(
                        f"Filtrage attributaire : {filter_spec['field']} "
                        f"{operator} {filter_spec['value']}"
                    ),
                    node_type="attribute_filter",
                    config={
                        "field": filter_spec["field"],
                        "operator": operator,
                        "value": filter_spec["value"],
                    },
                    attach_to_source=True if parallel_filters else False,
                    branch_index=index if parallel_filters else 0,
                    branch_id=index if parallel_filters else 0,
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

    if not steps and needs_mapping_guidance(objective):
        choice_id = (
            "dedupe_essential"
            if wants_data_cleaning_intent(objective) and not wants_mapping_intent(objective)
            else "snake_case"
        )
        if mapping_has_explicit_detail(objective, schema_columns):
            choice = resolve_mapping_choice(choice_id, schema_columns)
            if choice:
                steps.append(
                    StepDefinition(
                        kind="mapping",
                        summary=mapping_step_summary(choice_id),
                        node_type=str(choice["node_type"]),
                        config=dict(choice.get("config") or {}),
                    )
                )

    if not steps:
        steps.append(_inspect_step())

    notices: List[str] = []
    if needs_mapping_guidance(objective) and not mapping_has_explicit_detail(
        objective, schema_columns
    ):
        for option in build_mapping_choice_options(schema_columns):
            notices.append(f"{option['label']} — {option['description']}")
    return _expand_geometry_heal_steps(steps, inspect, notices), notices


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
    """Place le prochain nœud à droite de l'ancre (Y décalé si branche parallèle)."""
    anchor_node = find_node(graph, anchor_id)
    if not anchor_node:
        for node in graph_nodes(graph):
            if str(node.get("id")) == str(anchor_id):
                anchor_node = node
                break
    origin = _node_position(anchor_node)
    return {
        "x": origin["x"] + ARCHITECT_STEP_OFFSET_X,
        "y": origin["y"] + ARCHITECT_BRANCH_OFFSET_Y * max(0, branch_index),
    }


def _data_parent_id(
    *,
    source_node_id: str,
    previous_steps: List[Dict[str, Any]],
    step: StepDefinition,
    step_index: int,
    graph: Dict[str, Any],
) -> str:
    """Parent métier (reader ou nœud précédent dans la même branche)."""
    if step.attach_to_source:
        return str(source_node_id)
    branch_id = step.branch_id
    for prev in reversed(previous_steps):
        if not isinstance(prev, dict) or not prev.get("node_id"):
            continue
        prev_branch = prev.get("branch_id")
        if prev_branch is not None and int(prev_branch) != int(branch_id):
            continue
        if prev_branch is None and step_index > 0:
            prev_index = prev.get("index")
            if prev_index is not None and int(prev_index) != step_index - 1:
                continue
        candidate = str(prev["node_id"])
        node = find_node(graph, candidate)
        if not _is_auto_architect_node(node):
            return candidate
    if step_index > 0 and step_index - 1 < len(previous_steps):
        prev = previous_steps[step_index - 1]
        if isinstance(prev, dict) and prev.get("node_id"):
            candidate = str(prev["node_id"])
            node = find_node(graph, candidate)
            if not _is_auto_architect_node(node):
                return candidate
    return str(source_node_id)


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
    inspect = enrich_inspect_geometry_flags(inspect_input_schema(source_node_id, graph))
    steps, geometry_notices = build_step_plan(global_objective, inspect)
    global_plan = format_plan_labels(steps)
    proactive_suggestions = build_proactive_suggestions(
        global_objective,
        inspect,
        [step.kind for step in steps],
    )
    schema_fields = inspect.get("fields") if isinstance(inspect.get("fields"), list) else []
    schema_columns = [
        str(item.get("name"))
        for item in schema_fields
        if isinstance(item, dict) and item.get("name")
    ]
    if needs_mapping_guidance(global_objective) and not mapping_has_explicit_detail(
        global_objective, schema_columns
    ):
        mapping_hints = [
            f"{opt['label']} — {opt['description']}"
            for opt in build_mapping_choice_options(schema_columns)
        ]
        proactive_suggestions = mapping_hints + [
            item for item in proactive_suggestions if item not in mapping_hints
        ]

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
            "proactive_suggestions": proactive_suggestions,
            "geometry_notices": geometry_notices,
        }

    step = steps[current_step_index]
    data_parent_id = _data_parent_id(
        source_node_id=source_node_id,
        previous_steps=previous_steps,
        step=step,
        step_index=current_step_index,
        graph=graph,
    )
    if step.attach_to_source:
        layout_anchor_id = _anchor_node_id(
            source_node_id,
            previous_steps,
            0,
            graph=graph,
            layout_anchor_node_id=layout_anchor_node_id,
        )
        position = _layout_next_position(
            graph,
            layout_anchor_id,
            branch_index=step.branch_index,
        )
    else:
        layout_anchor_id = data_parent_id
        position = _layout_next_position(
            graph,
            layout_anchor_id,
            branch_index=0,
        )

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
            "from_node_id": data_parent_id,
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
        "anchor_node_id": data_parent_id,
        "layout_anchor_node_id": layout_anchor_id,
        "attach_to_source": step.attach_to_source,
        "branch_index": step.branch_index,
        "branch_id": step.branch_id,
        "proactive_suggestions": proactive_suggestions,
        "geometry_notices": geometry_notices,
    }
