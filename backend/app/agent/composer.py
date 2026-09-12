"""Planificateur Composer : thoughts, tool calls et diffs de code."""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Iterable, List, Optional

from app.agent.tools import (
    execute_tool,
    graph_edges,
    graph_nodes,
    node_type_of,
    tool_call_summary,
)

_FILTER_RE = re.compile(
    r"(?:filtre(?:r)?|filter)(?:\s+la)?(?:\s+colonne|\s+column)?\s*['\"]?(?P<field>[A-Za-z_][\w]*)['\"]?"
    r"\s*(?P<op>>=|<=|>|<|==|=)\s*['\"]?(?P<value>-?\d+(?:[.,]\d+)?)['\"]?",
    re.IGNORECASE,
)
_SIMPLE_FILTER_RE = re.compile(
    r"['\"](?P<field>[A-Za-z_][\w]*)['\"]\s*(?P<op>>=|<=|>|<|==|=)\s*(?P<value>-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)


def _is_reader(ntype: str) -> bool:
    return ntype.endswith("_reader") or ntype in {"file_reader"}


def _is_csv_reader(ntype: str, node: Dict[str, Any]) -> bool:
    if ntype == "csv_reader":
        return True
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    params = data.get("params") if isinstance(data.get("params"), dict) else {}
    path = str(params.get("path") or params.get("file") or "").lower()
    return path.endswith(".csv")


def _upstream_input_node(
    graph: Optional[Dict[str, Any]], node_id: str
) -> Optional[Dict[str, Any]]:
    nodes = graph_nodes(graph)
    by_id = {str(n.get("id")): n for n in nodes}
    for edge in graph_edges(graph):
        if str(edge.get("target")) == str(node_id):
            source = by_id.get(str(edge.get("source")))
            if source:
                return source
    return None


def find_source_node(
    graph: Optional[Dict[str, Any]],
    selected_node_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    nodes = graph_nodes(graph)
    if selected_node_id:
        for node in nodes:
            if str(node.get("id")) == str(selected_node_id):
                if node_type_of(node) == "composer_agent":
                    upstream = _upstream_input_node(graph, selected_node_id)
                    if upstream:
                        return upstream
                return node
    csv_nodes = [n for n in nodes if _is_csv_reader(node_type_of(n), n)]
    if csv_nodes:
        return csv_nodes[0]
    readers = [n for n in nodes if _is_reader(node_type_of(n))]
    if readers:
        return readers[0]
    return nodes[0] if nodes else None


def parse_attribute_filter(prompt: str) -> Optional[Dict[str, str]]:
    text = prompt or ""
    match = _FILTER_RE.search(text) or _SIMPLE_FILTER_RE.search(text)
    if not match:
        return None
    op_raw = match.group("op").lower()
    op_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "eq", "==": "eq"}
    operator = op_map.get(op_raw, op_raw if op_raw in {"gt", "lt", "eq"} else "gt")
    value = match.group("value").replace(",", ".")
    return {
        "field": match.group("field"),
        "operator": operator,
        "value": value,
    }


def detect_export_writer(prompt: str) -> Optional[str]:
    text = (prompt or "").lower()
    if "geopackage" in text or "gpkg" in text:
        return "gpkg_writer"
    if "geojson" in text:
        return "geojson_writer"
    if re.search(r"shapefile|\.shp\b|\bshp\b|vector_writer", text, re.IGNORECASE):
        return "shapefile_writer"
    if "postgis" in text:
        return "postgis_writer"
    if re.search(r"\bcsv\b", text) and re.search(r"export|écris|ecris|writer|sortie", text):
        return "csv_writer"
    return None


def _wants_python(prompt: str) -> bool:
    text = (prompt or "").lower()
    return any(token in text for token in ("python", "geopandas", "script", "sql"))


def _wants_analysis(prompt: str) -> bool:
    text = (prompt or "").lower()
    if re.search(r"\b(?:lire|lecture)\b", text):
        return True
    return any(
        token in text
        for token in (
            "analyse",
            "analyser",
            "décri",
            "decri",
            "explore",
            "inspect",
            "schéma",
            "schema",
            "colonnes",
            "colonne",
            "aperçu",
            "apercu",
            "données d'entrée",
            "donnees d'entree",
            "données en entrée",
            "input data",
        )
    )


def _format_schema_thought(inspect: Dict[str, Any]) -> str:
    if not inspect.get("ok"):
        err = inspect.get("error") or "inspection impossible"
        return (
            f"{err} — branchez un reader amont au Composer et exécutez « Test step » "
            "sur ce reader pour remplir l'aperçu."
        )
    fields = inspect.get("fields") if isinstance(inspect.get("fields"), list) else []
    names = ", ".join(
        str(item.get("name"))
        for item in fields[:12]
        if isinstance(item, dict) and item.get("name")
    )
    extra = f" (+{len(fields) - 12} autres)" if len(fields) > 12 else ""
    fc = inspect.get("feature_count")
    geom = inspect.get("geometry") or "—"
    crs = inspect.get("crs") or "non déterminé"
    label = inspect.get("label") or inspect.get("node_id")
    ntype = inspect.get("node_type") or "?"
    parts = [
        f"Schéma amont « {label} » ({ntype}) :",
    ]
    if fields:
        parts.append(f"{len(fields)} attribut(s) — {names}{extra}.")
    else:
        parts.append(
            "aucune colonne dans l'aperçu (exécutez le nœud amont pour charger des entités)."
        )
    if fc is not None:
        parts.append(f"Échantillon : {fc} entité(s).")
    parts.append(f"Géométrie : {geom}. CRS : {crs}.")
    return " ".join(parts)


_CC_ZONE_RE = re.compile(r"\bcc\s*[-_]?(\d{2})\b", re.IGNORECASE)


def _parse_cc_zone_crs(prompt: str) -> Optional[str]:
    """Lambert-93 Conique Conforme : CC42–CC50 → EPSG:3942–3950 (CC43 = EPSG:3943)."""
    match = _CC_ZONE_RE.search(prompt or "")
    if not match:
        return None
    zone = int(match.group(1))
    if 42 <= zone <= 50:
        return f"EPSG:{3900 + zone}"
    return None


def _wants_reproject(prompt: str) -> bool:
    text = (prompt or "").lower()
    if _parse_cc_zone_crs(text):
        return True
    return any(
        token in text
        for token in (
            "projection",
            "reproj",
            "reproject",
            "crs",
            "epsg",
            "lambert",
            "wgs84",
            "wgs 84",
            "mercator",
            "coordonn",
            "système de coord",
            "systeme de coord",
        )
    )


def parse_target_crs(prompt: str) -> str:
    text = prompt or ""
    match = re.search(r"EPSG\s*:?\s*(\d{4,6})", text, re.IGNORECASE)
    if match:
        return f"EPSG:{match.group(1)}"
    cc_crs = _parse_cc_zone_crs(text)
    if cc_crs:
        return cc_crs
    lower = text.lower()
    if "3857" in lower or "mercator" in lower:
        return "EPSG:3857"
    if "4326" in lower or "wgs" in lower:
        return "EPSG:4326"
    if "3945" in lower:
        return "EPSG:3945"
    if "3946" in lower:
        return "EPSG:3946"
    if "32631" in lower or "utm 31" in lower or "utm31" in lower:
        return "EPSG:32631"
    if "32632" in lower or "utm 32" in lower or "utm32" in lower:
        return "EPSG:32632"
    return "EPSG:2154"


def _source_position(source: Optional[Dict[str, Any]]) -> Dict[str, float]:
    if not source:
        return {"x": 120.0, "y": 180.0}
    pos = source.get("position") if isinstance(source.get("position"), dict) else {}
    return {"x": float(pos.get("x") or 120), "y": float(pos.get("y") or 180)}


def unified_diff(previous: str, updated: str, filename: str = "transform.py") -> str:
    old_lines = (previous or "").splitlines(keepends=True)
    new_lines = (updated or "").splitlines(keepends=True)
    if old_lines and not old_lines[-1].endswith("\n"):
        old_lines[-1] += "\n"
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"
    diff = difflib.unified_diff(
        old_lines or [""],
        new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="\n",
    )
    return "".join(diff)


def _event(event_type: str, **payload: Any) -> Dict[str, Any]:
    return {"type": event_type, **payload}


def _python_filter_code(field: str, operator: str, value: str) -> str:
    op_py = {">": ">", "gt": ">", ">=": ">=", "gte": ">=", "<": "<", "lt": "<", "eq": "=="}.get(
        operator, ">"
    )
    return (
        "# Filtre attributaire généré par Composer\n"
        f"output_gdf = gdf[gdf['{field}'] {op_py} {value}]\n"
        "return output_gdf\n"
    )


def plan_composer(
    prompt: str,
    current_graph: Optional[Dict[str, Any]] = None,
    selected_node_id: Optional[str] = None,
    context_mentions: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Produit la séquence SSE (thought / tool_call / code_diff)."""
    graph = current_graph or {"nodes": [], "edges": []}
    mentions = [str(item) for item in (context_mentions or [])]
    source = find_source_node(graph, selected_node_id)
    source_id = str(source.get("id")) if source else (selected_node_id or "csv_reader-1")
    source_type = node_type_of(source) if source else "csv_reader"
    origin = _source_position(source)
    if selected_node_id:
        for node in graph_nodes(graph):
            if str(node.get("id")) == str(selected_node_id):
                origin = _source_position(node)
                break
    filter_spec = parse_attribute_filter(prompt)
    writer_type = detect_export_writer(prompt)
    target_crs = parse_target_crs(prompt) if _wants_reproject(prompt) else None
    events: List[Dict[str, Any]] = []

    thought_src = "CSV" if "csv" in source_type or "csv" in (prompt or "").lower() else "jeu de données"
    if "shapefile" in (prompt or "").lower() or source_type == "shapefile_reader":
        thought_src = "Shapefile"
    events.append(
        _event(
            "thought",
            content=f"Analyse du {thought_src} d'entrée et des mentions {mentions or ['@Input', '@Schema']}…",
        )
    )

    inspect_args = {"node_id": source_id}
    inspect_result = execute_tool("inspect_input_schema", inspect_args, graph)
    events.append(
        _event(
            "tool_call",
            name="inspect_input_schema",
            summary=tool_call_summary("inspect_input_schema", inspect_args),
            arguments=inspect_args,
            result=inspect_result,
        )
    )

    # Cas cible : CSV → attribute_filter → GeoPackage
    use_filter_writer = bool(filter_spec) and writer_type in {
        "gpkg_writer",
        "geojson_writer",
        "shapefile_writer",
        "csv_writer",
        "postgis_writer",
    }
    if not use_filter_writer and writer_type == "gpkg_writer":
        filter_spec = filter_spec or {
            "field": "POPULATION",
            "operator": "gt",
            "value": "5000",
        }
        use_filter_writer = True

    created_ids: Dict[str, str] = {}

    if use_filter_writer and filter_spec:
        op_label = {">": ">", "gt": ">", "gte": ">=", "lt": "<", "eq": "="}.get(
            filter_spec["operator"], filter_spec["operator"]
        )
        events.append(
            _event(
                "thought",
                content=(
                    f"Filtrage de la colonne '{filter_spec['field']}' "
                    f"{op_label} {filter_spec['value']}, "
                    "puis export vers un Writer GeoPackage."
                ),
            )
        )
        filter_args = {
            "node_type": "attribute_filter",
            "position": {"x": origin["x"] + 280, "y": origin["y"]},
            "config": {
                "field": filter_spec["field"],
                "operator": filter_spec["operator"] if filter_spec["operator"] != "gte" else "gt",
                "value": filter_spec["value"],
            },
        }
        filter_node = execute_tool("create_canvas_node", filter_args, graph)
        created_ids["attribute_filter"] = filter_node["id"]
        events.append(
            _event(
                "tool_call",
                name="create_canvas_node",
                summary="create_node(attribute_filter)",
                arguments=filter_args,
                result=filter_node,
            )
        )

        connect_filter_args = {
            "from_node_id": source_id,
            "from_port": "output",
            "to_node_id": filter_node["id"],
            "to_port": "input",
        }
        connect_filter = execute_tool("connect_nodes", connect_filter_args, graph)
        events.append(
            _event(
                "tool_call",
                name="connect_nodes",
                summary="connect(...)",
                arguments=connect_filter_args,
                result=connect_filter,
            )
        )

        out_type = writer_type or "gpkg_writer"
        writer_args = {
            "node_type": out_type,
            "position": {"x": origin["x"] + 560, "y": origin["y"]},
            "config": {},
        }
        writer_node = execute_tool("create_canvas_node", writer_args, graph)
        created_ids[out_type] = writer_node["id"]
        events.append(
            _event(
                "tool_call",
                name="create_canvas_node",
                summary=f"create_node({out_type})",
                arguments=writer_args,
                result=writer_node,
            )
        )

        connect_writer_args = {
            "from_node_id": filter_node["id"],
            "from_port": "output",
            "to_node_id": writer_node["id"],
            "to_port": "input",
        }
        connect_writer = execute_tool("connect_nodes", connect_writer_args, graph)
        events.append(
            _event(
                "tool_call",
                name="connect_nodes",
                summary="connect(...)",
                arguments=connect_writer_args,
                result=connect_writer,
            )
        )

        if _wants_python(prompt):
            code = _python_filter_code(
                filter_spec["field"],
                filter_spec["operator"],
                filter_spec["value"],
            )
            py_args = {
                "node_type": "python_caller",
                "position": {"x": origin["x"] + 280, "y": origin["y"] + 140},
                "config": {"language": "python", "code": code},
            }
            py_node = execute_tool("create_canvas_node", py_args, graph)
            code_patch = execute_tool(
                "update_node_code",
                {"node_id": py_node["id"], "code": code, "language": "python"},
                graph,
            )
            events.append(
                _event(
                    "code_diff",
                    node_id=py_node["id"],
                    language="python",
                    diff=unified_diff("", code, "transform.py"),
                    code=code,
                    result=code_patch,
                )
            )

    elif _wants_python(prompt) and filter_spec:
        code = _python_filter_code(
            filter_spec["field"],
            filter_spec["operator"],
            filter_spec["value"],
        )
        py_args = {
            "node_type": "python_caller",
            "position": {"x": origin["x"] + 280, "y": origin["y"]},
            "config": {"language": "python", "code": code},
        }
        py_node = execute_tool("create_canvas_node", py_args, graph)
        events.append(
            _event(
                "tool_call",
                name="create_canvas_node",
                summary="create_node(python_caller)",
                arguments=py_args,
                result=py_node,
            )
        )
        connect_args = {
            "from_node_id": source_id,
            "from_port": "output",
            "to_node_id": py_node["id"],
            "to_port": "input",
        }
        events.append(
            _event(
                "tool_call",
                name="connect_nodes",
                summary="connect(...)",
                arguments=connect_args,
                result=execute_tool("connect_nodes", connect_args, graph),
            )
        )
        code_patch = execute_tool(
            "update_node_code",
            {"node_id": py_node["id"], "code": code, "language": "python"},
            graph,
        )
        events.append(
            _event(
                "tool_call",
                name="update_node_code",
                summary=tool_call_summary("update_node_code", {"node_id": py_node["id"]}),
                arguments={"node_id": py_node["id"], "code": code, "language": "python"},
                result=code_patch,
            )
        )
        events.append(
            _event(
                "code_diff",
                node_id=py_node["id"],
                language="python",
                diff=unified_diff("", code, "transform.py"),
                code=code,
            )
        )
    elif target_crs:
        source_crs = inspect_result.get("crs") or "EPSG:4326"
        events.append(
            _event(
                "thought",
                content=_format_schema_thought(inspect_result),
            )
        )
        events.append(
            _event(
                "thought",
                content=(
                    f"Reprojection {source_crs} → {target_crs} "
                    "(nœud Transform Coordinate System)."
                ),
            )
        )
        reproj_args = {
            "node_type": "reprojector",
            "position": {"x": origin["x"], "y": origin["y"]},
            "config": {
                "source_crs": source_crs if str(source_crs).upper().startswith("EPSG") else "EPSG:4326",
                "target_crs": target_crs,
            },
        }
        reproj_node = execute_tool("create_canvas_node", reproj_args, graph)
        created_ids["reprojector"] = reproj_node["id"]
        events.append(
            _event(
                "tool_call",
                name="create_canvas_node",
                summary="create_node(reprojector)",
                arguments=reproj_args,
                result=reproj_node,
            )
        )
    else:
        events.append(
            _event(
                "thought",
                content=_format_schema_thought(inspect_result),
            )
        )
        if _wants_analysis(prompt):
            events.append(
                _event(
                    "thought",
                    content=(
                        "Pour remplacer ce bloc par des nœuds ETL, précisez par exemple : "
                        "« filtre POPULATION > 5000 puis export GeoPackage »."
                    ),
                )
            )
        else:
            events.append(
                _event(
                    "thought",
                    content=(
                        "Aucune séquence filtre/export détectée — inspection uniquement. "
                        "Ajoutez une consigne de transformation pour générer des nœuds."
                    ),
                )
            )

    sequence = [
        item.get("summary")
        for item in events
        if item.get("type") == "tool_call" and item.get("name") in {"create_canvas_node", "connect_nodes"}
    ]
    events.append(
        _event(
            "done",
            sequence=sequence,
            created_ids=created_ids,
            source_node_id=source_id,
        )
    )
    return events


def extract_tool_sequence(events: List[Dict[str, Any]]) -> List[str]:
    return [
        str(item.get("summary"))
        for item in events
        if item.get("type") == "tool_call"
        and item.get("name") in {"create_canvas_node", "connect_nodes"}
    ]
