"""Import / export workspace (.fmw / .fmwt) vers le graphe 4GIx."""

from __future__ import annotations

import html
import json
import re
import zlib
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from app.nodes import NODE_REGISTRY, list_catalog

# Nom factory / transformer → node_type 4GIx
FMW_FACTORY_TO_NODE: Dict[str, str] = {
    "geometryvalidator": "geometry_validator",
    "geometryfilter": "geometry_filter",
    "snapper": "snapper",
    "orientor": "orientor",
    "bufferer": "bufferer",
    "buffer": "bufferer",
    "clipper": "clipper",
    "dissolver": "dissolver",
    "areaonareaoverlayer": "area_on_area_overlayer",
    "lineonlineoverlayer": "line_on_line_overlayer",
    "centerpointreplacer": "centroid_extractor",
    "centroidextractor": "centroid_extractor",
    "boundingboxreplacer": "bounding_box_replacer",
    "densifier": "densifier",
    "generalizer": "generalizer",
    "douglaspeucker": "generalizer",
    "featuremerger": "feature_merger",
    "spatialrelator": "spatial_relator",
    "spatialfilter": "spatial_relator",
    "neighborfinder": "neighbor_finder",
    "attributemanager": "attribute_manager",
    "attributemapper": "attribute_mapper",
    "attributecreator": "attribute_manager",
    "attributeexposer": "attribute_manager",
    "tester": "tester",
    "testfilter": "test_filter",
    "listexploder": "list_exploder",
    "counter": "counter",
    "duplicatefilter": "duplicate_filter",
    "reprojector": "reprojector",
    "reproject": "reprojector",
    "coordinatesystemsetter": "reprojector",
    "spatialjoin": "spatial_join",
    "ogrgeojson": "geojson_reader",
    "geojson": "geojson_reader",
    "geojsonreader": "geojson_reader",
    "postgisreader": "postgis_reader",
    "postgiswriter": "postgis_writer",
    "shapereader": "shapefile_reader",
    "shapefilereader": "shapefile_reader",
    "csvreader": "file_reader",
    "filereader": "file_reader",
    "featureReader": "file_reader",
    "featurereader": "file_reader",
    "filewriter": "file_writer",
    "logwriter": "log_writer",
    "ifcbimreader": "ifc_bim_reader",
    "dxfreader": "dxf_reader",
    "geotiffreader": "geotiff_raster_reader",
    "restwfsreader": "rest_wfs_reader",
    "datetimeconverter": "attribute_manager",
    "dateformatter": "attribute_manager",
    "timestampconverter": "attribute_manager",
    "postgresqlwriter": "postgis_writer",
    "postgreswriter": "postgis_writer",
    "transformdatetopostgres": "attribute_manager",
    "recordmanager": "attribute_manager",
    "vertexcreator": "attribute_manager",
    "featuretypefilter": "test_filter",
    "spatialfilterfactory": "spatial_relator",
}

NODE_TO_FMW_FACTORY: Dict[str, str] = {
    "geometry_validator": "GeometryValidator",
    "geometry_filter": "GeometryFilter",
    "snapper": "Snapper",
    "orientor": "Orientor",
    "bufferer": "Bufferer",
    "clipper": "Clipper",
    "dissolver": "Dissolver",
    "area_on_area_overlayer": "AreaOnAreaOverlayer",
    "line_on_line_overlayer": "LineOnLineOverlayer",
    "centroid_extractor": "CenterPointReplacer",
    "bounding_box_replacer": "BoundingBoxReplacer",
    "densifier": "Densifier",
    "generalizer": "Generalizer",
    "feature_merger": "FeatureMerger",
    "spatial_relator": "SpatialRelator",
    "neighbor_finder": "NeighborFinder",
    "attribute_manager": "AttributeManager",
    "attribute_mapper": "AttributeMapper",
    "tester": "Tester",
    "test_filter": "TestFilter",
    "list_exploder": "ListExploder",
    "counter": "Counter",
    "duplicate_filter": "DuplicateFilter",
    "reprojector": "Reprojector",
    "spatial_join": "SpatialRelator",
    "geojson_reader": "OGRGeoJSON",
    "shapefile_reader": "ShapefileReader",
    "postgis_reader": "PostGISReader",
    "postgis_writer": "PostGISWriter",
    "file_reader": "CSVReader",
    "file_writer": "ShapefileWriter",
    "log_writer": "LogWriter",
    "ifc_bim_reader": "IFCBIMReader",
    "dxf_reader": "DXFReader",
    "geotiff_raster_reader": "GeoTIFFReader",
    "rest_wfs_reader": "WFSReader",
}

PORT_MAP = {
    "output": "output",
    "input": "input",
    "<output>": "output",
    "<input>": "input",
    "passed": "passed",
    "failed": "failed",
    "rejected": "rejected",
    "<rejected>": "rejected",
    "inside": "inside",
    "outside": "outside",
    "merged": "merged",
    "unique": "unique",
    "duplicate": "duplicate",
}

OUTPUT_FEAT_HANDLE = {
    "OUTPUT": "output",
    "PASSED": "passed",
    "FAILED": "failed",
    "REJECTED": "rejected",
    "<REJECTED>": "rejected",
    "INSIDE": "inside",
    "OUTSIDE": "outside",
    "MERGED": "merged",
    "SPLIT": "output",
    "THINNED": "output",
    "REPROJECTED": "output",
    "CREATED": "output",
    "RESULT": "output",
    "LAS": "output",
}

FACTORY_CLASS_HINT = {
    "testfactory": "tester",
    "clippingfactory": "clipper",
    "dissolverfactory": "dissolver",
    "buffererfactory": "bufferer",
    "reprojector": "reprojector",
    "queryfactory": "file_reader",
}

FALLBACK_NODE_TYPE = "attribute_manager"

FMW_ENCRYPTED_HINT = (
    "Impossible d'extraire des transformateurs de ce fichier (FMW0001 souvent chiffré). "
    "One-shot : ouvrir dans l'éditeur d'origine et « Save As » .fmw texte, ou exporter un JSON 4GIx. "
    "Sinon, recréez le flux avec la palette — l'exécution reste 100 % 4GIx, en natif."
)


def _raw_has_workbench_markers(raw: bytes) -> bool:
    window = raw[: min(len(raw), 3_000_000)]
    upper = window.upper()
    markers = (
        b"#! <WORKSPACE",
        b"# ! <WORKSPACE",
        b"<TRANSFORMER",
        b"FACTORY_DEF",
        b"<FEAT_LINK",
    )
    return any(marker in window or marker in upper for marker in markers)


def extract_embedded_workbench_text(raw: bytes) -> str | None:
    """Tente d'extraire du texte Workbench embarqué dans un .fmw hybride."""
    for marker in (b"#! <WORKSPACE", b"# ! <WORKSPACE", b"#!\n#! <WORKSPACE"):
        idx = raw.find(marker)
        if idx >= 0:
            chunk = raw[idx : idx + 12_000_000]
            return chunk.decode("utf-8", errors="ignore")
    idx = raw.upper().find(b"<TRANSFORMER")
    if idx >= 0:
        start = raw.rfind(b"#!", 0, idx)
        if start < 0:
            start = max(0, idx - 500_000)
        chunk = raw[start : start + 12_000_000]
        return chunk.decode("utf-8", errors="ignore")
    return None


def decode_fmw_bytes(raw: bytes) -> str:
    """Décode un .fmw — ne lève pas sur binaire (parse_fmw_bytes gère les tentatives)."""
    if not raw:
        raise ValueError("Fichier vide.")
    embedded = extract_embedded_workbench_text(raw)
    if embedded and (
        "<TRANSFORMER" in embedded.upper() or "FACTORY_DEF" in embedded
    ):
        return _normalize_fmw_text(embedded)
    if raw.startswith(b"\xff\xfe"):
        text = raw.decode("utf-16-le")
    elif raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16-be")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
    return _normalize_fmw_text(text)


def detect_fmw_binary_format(raw: bytes) -> str:
    if _raw_has_workbench_markers(raw):
        return "text"
    head = raw[:512]
    if head.startswith(b"FMW0001") or b"FMW0001" in head:
        return "binary_encrypted"
    if head.startswith(b"FMW") and b"<TRANSFORMER" not in raw[: min(len(raw), 200_000)]:
        if raw[:8000].count(b"\x00") > 40:
            return "binary_encrypted"
    return "text"


def detect_fmw_text_format(text: str) -> str:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        return "json"
    first = stripped.split("\n", 1)[0].strip()
    if first.startswith("FMW") and "{" in text[:4000]:
        return "json"
    if "#! <WORKSPACE" in text or "<TRANSFORMER" in text.upper():
        return "workbench_xml"
    if "FACTORY_DEF" in text:
        return "mapping"
    return "unknown"


def _extract_gui_text(text: str) -> str:
    """Extrait la section XML Workbench (#! … </WORKSPACE>)."""
    chunks: List[str] = []
    in_workspace = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#!"):
            continue
        payload = stripped[2:].lstrip()
        if payload.startswith(">"):
            payload = payload[1:].lstrip()
        if "<WORKSPACE" in payload or in_workspace:
            in_workspace = True
            chunks.append(payload)
            if "</WORKSPACE>" in payload:
                break
    if chunks:
        return "\n".join(chunks)
    gui_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#!"):
            payload = stripped[2:].lstrip().lstrip(">")
            if payload.startswith("<"):
                gui_lines.append(payload)
    return "\n".join(gui_lines)


def _normalize_fmw_text(text: str) -> str:
    lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# !"):
            lines.append("#!" + stripped[3:].lstrip())
        else:
            lines.append(line)
    return "\n".join(lines)


def _resolve_node_type(
    fme_type: str,
    label: str,
    warnings: List[str],
) -> str:
    for candidate in (fme_type, label):
        mapped = map_fme_type(candidate)
        if mapped:
            return mapped
    combined = _normalize_fme_type(f"{fme_type}{label}")
    if "postgis" in combined or "postgres" in combined:
        if "writer" in combined or "transform" in combined or "export" in combined:
            mapped = "postgis_writer"
            if mapped in NODE_REGISTRY:
                return mapped
    if "geojson" in combined or "json" in combined:
        mapped = map_fme_type("geojson_reader")
        if mapped:
            return mapped
    safe_type = _sanitize_label(fme_type, fallback="Workbench")
    safe_label = _sanitize_label(label, fallback=safe_type)
    warnings.append(
        f"Type factory non mappé: {safe_type} ({safe_label}) → {FALLBACK_NODE_TYPE}",
    )
    return FALLBACK_NODE_TYPE


def _catalog_index() -> Dict[str, dict]:
    return {entry["node_type"]: entry for entry in list_catalog()}


def _normalize_fme_type(raw: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (raw or "").lower())


def map_fme_type(fme_type: str) -> Optional[str]:
    key = _normalize_fme_type(fme_type)
    if key in FMW_FACTORY_TO_NODE:
        mapped = FMW_FACTORY_TO_NODE[key]
        if mapped in NODE_REGISTRY:
            return mapped
    for node_type in NODE_REGISTRY:
        if _normalize_fme_type(node_type) == key:
            return node_type
    return None


def _sanitize_label(raw: Optional[str], *, fallback: str = "") -> str:
    if raw is None:
        return fallback or "Transformer"
    if not isinstance(raw, str):
        return fallback or "Transformer"
    label = html.unescape(str(raw).strip())
    if label.startswith("{") and label.endswith("}"):
        label = label[1:-1].strip()
    if label in ("{", "}", ""):
        label = ""
    label = label.strip('"').strip("'")
    return label or fallback or "Transformer"


def _parse_position(raw: Optional[str]) -> Optional[Tuple[float, float]]:
    if not raw:
        return None
    parts = re.split(r"[,\s]+", str(raw).strip())
    nums = [float(p) for p in parts if re.match(r"^-?\d+(\.\d+)?$", p)]
    if len(nums) >= 2:
        return nums[0], nums[1]
    if len(nums) == 1:
        return nums[0], 0.0
    return None


def _port_handle(raw: Optional[str], default: str = "output") -> str:
    if not raw:
        return default
    key = raw.strip().lower().replace(" ", "_")
    key = key.strip("<>")
    return PORT_MAP.get(key, key if key else default)


def _attr_from_fragment(fragment: str, name: str) -> Optional[str]:
    match = re.search(rf'{name}="([^"]*)"', fragment, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_workspace_xml(text: str) -> Optional[str]:
    xml_lines: List[str] = []
    in_workspace = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#!"):
            continue
        payload = stripped[2:].lstrip()
        if payload.startswith(">"):
            payload = payload[1:].lstrip()
        if payload.startswith("<WORKSPACE") or in_workspace:
            in_workspace = True
            xml_lines.append(payload)
            if payload.startswith("</WORKSPACE") or payload == "</WORKSPACE>":
                break
    if not xml_lines:
        return None
    xml = "\n".join(xml_lines)
    if not xml.strip().startswith("<"):
        return None
    return xml


def _build_flow_node(
    node_id: str,
    node_type: str,
    label: str,
    position: Tuple[float, float],
    catalog: Dict[str, dict],
    params: Optional[Dict[str, Any]] = None,
    *,
    fme_source_type: Optional[str] = None,
) -> dict:
    entry = catalog.get(node_type, {})
    category = entry.get("category") or "Transformer"
    safe_label = _sanitize_label(label, fallback=entry.get("title") or node_type)
    merged_params = dict(params or {})
    if fme_source_type:
        merged_params.setdefault("fme_source_type", fme_source_type)
    return {
        "id": node_id,
        "type": "etl",
        "position": {"x": position[0], "y": position[1]},
        "data": {
            "label": safe_label,
            "nodeType": node_type,
            "category": category,
            "isSpatial": bool(entry.get("is_spatial")),
            "params": merged_params or {},
            "schema": entry.get("schema") or {},
            "status": "idle",
            "inputHandles": entry.get("input_handles") or ["input"],
            "outputHandles": entry.get("output_handles") or ["output"],
            "paletteGroup": entry.get("palette_group") or "",
            "notes": "",
            "disabled": False,
        },
    }


def _make_gix_id(node_type: str, fme_id: str, used: Set[str]) -> str:
    base = f"{node_type}-{fme_id}"
    candidate = base
    seq = 2
    while candidate in used:
        candidate = f"{base}-{seq}"
        seq += 1
    used.add(candidate)
    return candidate


def _output_feats_from_block(block: str) -> List[str]:
    names = re.findall(
        r'<OUTPUT_FEAT\s+NAME="([^"]+)"',
        block,
        flags=re.IGNORECASE,
    )
    return [html.unescape(name) for name in names]


def _fo_index_to_handle(output_feats: List[str], fo_index: int) -> str:
    if 0 <= fo_index < len(output_feats):
        key = output_feats[fo_index].strip().upper()
        return OUTPUT_FEAT_HANDLE.get(key, _port_handle(key, "output"))
    return "output"


def _parse_port_desc(desc: Optional[str], output_feats: List[str], *, is_source: bool) -> str:
    if not desc:
        return "output" if is_source else "input"
    desc = desc.strip().lower()
    if desc.startswith("fi"):
        return "input"
    fo_match = re.match(r"fo\s*(\d+)", desc)
    if fo_match:
        return _fo_index_to_handle(output_feats, int(fo_match.group(1)))
    return _port_handle(desc, "output" if is_source else "input")


def _normalize_canvas_positions(nodes: List[dict]) -> None:
    if not nodes:
        return
    xs = [float(n["position"]["x"]) for n in nodes]
    ys = [float(n["position"]["y"]) for n in nodes]
    min_x, min_y = min(xs), min(ys)
    max_y = max(ys)
    flip_y = max_y <= 0 and min_y < 0
    for node in nodes:
        x = float(node["position"]["x"]) - min_x + 80.0
        y = float(node["position"]["y"]) - min_y + 80.0
        if flip_y:
            y = (max_y - float(node["position"]["y"])) + 80.0
        node["position"] = {"x": x, "y": y}


def _layout_hierarchical(nodes: List[dict], edges: List[dict]) -> None:
    if not nodes:
        return
    ids = [node["id"] for node in nodes]
    id_set = set(ids)
    adj: Dict[str, Set[str]] = {node_id: set() for node_id in ids}
    indeg: Dict[str, int] = {node_id: 0 for node_id in ids}
    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if src in id_set and tgt in id_set and src != tgt:
            if tgt not in adj[src]:
                adj[src].add(tgt)
                indeg[tgt] = indeg.get(tgt, 0) + 1

    layers: Dict[str, int] = {}
    queue: deque[str] = deque([node_id for node_id in ids if indeg.get(node_id, 0) == 0])
    if not queue:
        queue = deque(ids)
    while queue:
        current = queue.popleft()
        layer = layers.get(current, 0)
        for nxt in adj.get(current, ()):
            layers[nxt] = max(layers.get(nxt, 0), layer + 1)
            indeg[nxt] -= 1
            if indeg[nxt] <= 0:
                queue.append(nxt)

    for index, node_id in enumerate(ids):
        if node_id not in layers:
            layers[node_id] = index % 5

    by_layer: Dict[int, List[str]] = defaultdict(list)
    for node_id, layer in layers.items():
        by_layer[layer].append(node_id)

    node_by_id = {node["id"]: node for node in nodes}
    for layer, peers in by_layer.items():
        for index, node_id in enumerate(sorted(peers)):
            node_by_id[node_id]["position"] = {
                "x": 80.0 + layer * 260.0,
                "y": 80.0 + index * 130.0,
            }


def _parse_workbench_gui(
    text: str,
    catalog: Dict[str, dict],
) -> Tuple[List[dict], List[dict], Dict[str, List[str]], List[str]]:
    """Parse le XML Workbench embarqué (#! <TRANSFORMER> … <FEAT_LINK> …)."""
    warnings: List[str] = []
    nodes: List[dict] = []
    id_map: Dict[str, str] = {}
    output_ports: Dict[str, List[str]] = {}
    used_ids: Set[str] = set()
    gui_text = _extract_gui_text(text) or text

    transformer_blocks = re.findall(
        r"(<TRANSFORMER\b.*?(?:</TRANSFORMER>|/>))",
        gui_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in transformer_blocks:
        fme_id = _attr_from_fragment(block, "IDENTIFIER")
        if not fme_id:
            continue
        fme_type = _attr_from_fragment(block, "TYPE") or "Transformer"
        xformer_name = _attr_from_fragment(block, "INSTANCENAME")
        if not xformer_name:
            parm_match = re.search(
                r'PARM_NAME="XFORMER_NAME"\s+PARM_VALUE="([^"]*)"',
                block,
                re.IGNORECASE,
            )
            if parm_match:
                xformer_name = html.unescape(parm_match.group(1))
        label = _sanitize_label(xformer_name, fallback=_sanitize_label(fme_type))
        node_type = _resolve_node_type(fme_type, label, warnings)
        pos_raw = _parse_position(_attr_from_fragment(block, "POSITION"))
        pos = pos_raw if pos_raw else (120.0, 120.0)
        gix_id = _make_gix_id(node_type, fme_id, used_ids)
        id_map[fme_id] = gix_id
        output_ports[gix_id] = _output_feats_from_block(block)
        nodes.append(
            _build_flow_node(
                gix_id,
                node_type,
                label,
                pos,
                catalog,
                fme_source_type=fme_type,
            )
        )

    feature_blocks = re.findall(
        r"(<FEATURE_TYPE\s+.*?</FEATURE_TYPE>)",
        gui_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for block in feature_blocks:
        fme_id = _attr_from_fragment(block, "IDENTIFIER")
        if not fme_id or fme_id in id_map:
            continue
        node_name = _attr_from_fragment(block, "NODE_NAME") or "Writer"
        keyword = (_attr_from_fragment(block, "KEYWORD") or "").upper()
        node_type = map_fme_type(keyword) or map_fme_type(node_name) or "postgis_writer"
        if node_type not in NODE_REGISTRY:
            node_type = "file_writer"
        pos_raw = _parse_position(_attr_from_fragment(block, "POSITION"))
        pos = pos_raw if pos_raw else (120.0, 120.0)
        label = _sanitize_label(node_name, fallback=node_type)
        gix_id = _make_gix_id(node_type, fme_id, used_ids)
        id_map[fme_id] = gix_id
        output_ports[gix_id] = ["OUTPUT"]
        nodes.append(_build_flow_node(gix_id, node_type, label, pos, catalog))

    edges: List[dict] = []
    link_fragments = re.findall(
        r"(<FEAT_LINK\s+.*?/>)",
        gui_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for index, fragment in enumerate(link_fragments):
        enabled = (_attr_from_fragment(fragment, "ENABLED") or "true").lower()
        if enabled == "false":
            continue
        src_fme = _attr_from_fragment(fragment, "SOURCE_NODE")
        tgt_fme = _attr_from_fragment(fragment, "TARGET_NODE")
        if not src_fme or not tgt_fme:
            continue
        if src_fme not in id_map or tgt_fme not in id_map:
            continue
        src_id = id_map[src_fme]
        tgt_id = id_map[tgt_fme]
        src_port = _parse_port_desc(
            _attr_from_fragment(fragment, "SOURCE_PORT_DESC"),
            output_ports.get(src_id, []),
            is_source=True,
        )
        tgt_port = _parse_port_desc(
            _attr_from_fragment(fragment, "TARGET_PORT_DESC"),
            [],
            is_source=False,
        )
        edges.append(
            {
                "id": f"e-{src_id}-{tgt_id}-{src_port}-{index}",
                "source": src_id,
                "target": tgt_id,
                "sourceHandle": src_port,
                "targetHandle": tgt_port,
                "animated": True,
            }
        )

    return nodes, edges, output_ports, warnings


def _parse_workspace_xml(xml: str, catalog: Dict[str, dict]) -> Tuple[List[dict], List[dict], List[str]]:
    root = ET.fromstring(xml)
    warnings: List[str] = []
    fme_nodes: List[dict] = []
    id_map: Dict[str, str] = {}
    used_ids: Set[str] = set()

    for elem in root.iter():
        tag = (elem.tag or "").upper()
        if tag not in {
            "TRANSFORMER",
            "READER",
            "WRITER",
            "SOURCE",
            "DESTINATION",
            "WORKSPACE_OBJECT",
            "OBJECT",
        }:
            continue
        fme_id = (
            elem.attrib.get("IDENTIFIER")
            or elem.attrib.get("ID")
            or elem.attrib.get("OBJECTID")
            or str(len(fme_nodes) + 1)
        )
        fme_type = (
            elem.attrib.get("TYPE")
            or elem.attrib.get("FACTORY")
            or elem.attrib.get("T")
            or elem.attrib.get("NAME")
            or tag
        )
        inst = _sanitize_label(
            elem.attrib.get("INSTANCENAME") or elem.attrib.get("LABEL"),
            fallback=_sanitize_label(fme_type),
        )
        pos_raw = _parse_position(
            elem.attrib.get("POSITION")
            or elem.attrib.get("POS")
            or elem.attrib.get("LOCATION")
            or elem.attrib.get("X_COORDINATE")
        )
        pos = pos_raw if pos_raw else (120.0, 120.0)
        node_type = map_fme_type(fme_type)
        if not node_type:
            warnings.append(f"Type factory non mappé: {fme_type} ({inst})")
            continue
        gix_id = _make_gix_id(node_type, str(fme_id), used_ids)
        id_map[str(fme_id)] = gix_id
        fme_nodes.append(_build_flow_node(gix_id, node_type, inst, pos, catalog))

    edges: List[dict] = []
    for elem in root.iter():
        tag = (elem.tag or "").upper()
        if tag not in {"LINK", "FEAT_LINK", "CONNECTION"}:
            continue
        src = elem.attrib.get("SOURCE") or elem.attrib.get("SOURCE_NODE") or elem.attrib.get("S")
        tgt = elem.attrib.get("TARGET") or elem.attrib.get("DEST_NODE") or elem.attrib.get("T")
        if not src or not tgt:
            continue
        src_port = _port_handle(
            elem.attrib.get("SOURCE_PORT") or elem.attrib.get("SPORT"),
            "output",
        )
        tgt_port = _port_handle(
            elem.attrib.get("TARGET_PORT") or elem.attrib.get("TPORT"),
            "input",
        )
        if src not in id_map or tgt not in id_map:
            continue
        edges.append(
            {
                "id": f"e-{id_map[src]}-{id_map[tgt]}-{src_port}",
                "source": id_map[src],
                "target": id_map[tgt],
                "sourceHandle": src_port,
                "targetHandle": tgt_port,
                "animated": True,
            }
        )
    return fme_nodes, edges, warnings


def _parse_factory_block(
    block: str,
    catalog: Dict[str, dict],
    used_ids: Set[str],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[Tuple[float, float]], Optional[str]]:
    """Retourne (factory_name, fme_type, gix_id, position, node_type)."""
    name_match = re.search(
        r'FACTORY_NAME\s+(?:"([^"]+)"|(\{[^}]+\})|(\S+))',
        block,
        re.IGNORECASE,
    )
    if not name_match:
        return None, None, None, None, None
    factory_name = _sanitize_label(
        name_match.group(1) or name_match.group(2) or name_match.group(3),
    )
    def_match = re.search(r"FACTORY_DEF\s+\S+\s+(\w+)", block, re.IGNORECASE)
    factory_class = (def_match.group(1) if def_match else "").lower()
    type_hint = FACTORY_CLASS_HINT.get(factory_class)
    fme_type = type_hint or factory_class.replace("factory", "")
    node_type = map_fme_type(fme_type) or map_fme_type(factory_name)
    if not node_type and factory_class:
        node_type = map_fme_type(factory_class)
    if not node_type:
        node_type = FALLBACK_NODE_TYPE

    x_coord = re.search(r"X_COORDINATE\s+(-?\d+(?:\.\d+)?)", block, re.IGNORECASE)
    y_coord = re.search(r"Y_COORDINATE\s+(-?\d+(?:\.\d+)?)", block, re.IGNORECASE)
    placement = _parse_position(_attr_from_fragment(block.replace("\n", " "), "POSITION"))
    if x_coord and y_coord:
        pos: Optional[Tuple[float, float]] = (float(x_coord.group(1)), float(y_coord.group(1)))
    else:
        pos = placement

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", factory_name)[:40] or node_type
    gix_id = _make_gix_id(node_type, slug, used_ids)
    return factory_name, fme_type, gix_id, pos, node_type


def _parse_mapping_factories(
    text: str,
    catalog: Dict[str, dict],
) -> Tuple[List[dict], List[dict], Dict[str, str], List[str]]:
    warnings: List[str] = []
    nodes: List[dict] = []
    name_to_gix: Dict[str, str] = {}
    used_ids: Set[str] = set()
    blocks = re.split(r"(?=FACTORY_DEF\s)", text, flags=re.IGNORECASE)
    for block in blocks:
        if "FACTORY_NAME" not in block.upper():
            continue
        factory_name, fme_type, gix_id, pos, node_type = _parse_factory_block(
            block,
            catalog,
            used_ids,
        )
        if not factory_name or not gix_id or not node_type:
            continue
        if " nuker" in factory_name.lower() or factory_name.lower().endswith("nuker"):
            continue
        name_to_gix[factory_name] = gix_id
        position = pos if pos else (120.0, 120.0)
        label = _sanitize_label(factory_name, fallback=fme_type or node_type)
        nodes.append(
            _build_flow_node(
                gix_id,
                node_type,
                label,
                position,
                catalog,
                fme_source_type=fme_type or factory_name,
            )
        )

    edges: List[dict] = []
    routed_re = re.compile(
        r"ROUTED_TO\s+"
        r'(?:"([^"]+)"|(\{[^}]+\})|(\S+))\s+'
        r"(\S+)\s+OUTPUT\s+TO\s+"
        r'(?:"([^"]+)"|(\{[^}]+\})|(\S+))\s+'
        r"(\S+)",
        re.IGNORECASE,
    )
    for index, match in enumerate(routed_re.finditer(text)):
        src_name = _sanitize_label(match.group(1) or match.group(2) or match.group(3))
        src_port = _port_handle(match.group(4), "output")
        tgt_name = _sanitize_label(match.group(5) or match.group(6) or match.group(7))
        tgt_port = _port_handle(match.group(8), "input")
        if src_name not in name_to_gix or tgt_name not in name_to_gix:
            continue
        src_id = name_to_gix[src_name]
        tgt_id = name_to_gix[tgt_name]
        edges.append(
            {
                "id": f"e-route-{index}",
                "source": src_id,
                "target": tgt_id,
                "sourceHandle": src_port,
                "targetHandle": tgt_port,
                "animated": True,
            }
        )

    if not edges:
        link_re = re.compile(
            r'LINK\s+"?([^"\s]+)"?\s+"?([^"\s]+)"?\s+"?([^"\s]+)"?\s+"?([^"\s]+)"?',
            re.IGNORECASE,
        )
        inst_map = {name: gid for name, gid in name_to_gix.items()}
        for idx, match in enumerate(link_re.finditer(text)):
            src_inst, src_port, tgt_inst, tgt_port = match.groups()
            src_inst = _sanitize_label(src_inst)
            tgt_inst = _sanitize_label(tgt_inst)
            if src_inst not in inst_map or tgt_inst not in inst_map:
                continue
            edges.append(
                {
                    "id": f"e-fallback-{idx}",
                    "source": inst_map[src_inst],
                    "target": inst_map[tgt_inst],
                    "sourceHandle": _port_handle(src_port),
                    "targetHandle": _port_handle(tgt_port, "input"),
                    "animated": True,
                }
            )

    return nodes, edges, name_to_gix, warnings


def _infer_mapping_edges(text: str, name_to_gix: Dict[str, str]) -> List[dict]:
    """Déduit des arêtes via OUTPUT FEATURE_TYPE → INPUT FEATURE_TYPE (section mapping)."""
    producers: Dict[str, Tuple[str, str]] = {}
    edges: List[dict] = []
    blocks = re.split(r"(?=FACTORY_DEF\s)", text, flags=re.IGNORECASE)
    for block in blocks:
        name_match = re.search(
            r'FACTORY_NAME\s+(?:"([^"]+)"|(\{[^}]+\})|(\S+))',
            block,
            re.IGNORECASE,
        )
        if not name_match:
            continue
        fname = _sanitize_label(
            name_match.group(1) or name_match.group(2) or name_match.group(3),
        )
        if fname not in name_to_gix:
            continue
        tgt_id = name_to_gix[fname]
        for match in re.finditer(
            r"OUTPUT\s+(PASSED|FAILED|RESULT|INSIDE|OUTSIDE|MERGED|ROUTED)\s+FEATURE_TYPE\s+(\S+)",
            block,
            re.IGNORECASE,
        ):
            sport = _port_handle(match.group(1), "output")
            producers[match.group(2)] = (tgt_id, sport)
        for match in re.finditer(r"OUTPUT\s+FEATURE_TYPE\s+(\S+)", block, re.IGNORECASE):
            feat = match.group(1)
            if feat not in producers:
                producers[feat] = (tgt_id, "output")
        for inp in re.findall(
            r"INPUT\s+(?:FEATURE_TYPE|CLIPPEE|CLIPPER)\s+(\S+)",
            block,
            re.IGNORECASE,
        ):
            if inp not in producers:
                continue
            src_id, sport = producers[inp]
            if src_id == tgt_id:
                continue
            edges.append(
                {
                    "id": f"e-inf-{src_id}-{tgt_id}-{len(edges)}",
                    "source": src_id,
                    "target": tgt_id,
                    "sourceHandle": sport,
                    "targetHandle": "input",
                    "animated": True,
                }
            )
    return edges


def parse_fmw(content: str, *, default_name: str = "Import .fmw") -> Dict[str, Any]:
    catalog = _catalog_index()
    text_format = detect_fmw_text_format(content)
    name = default_name
    title_match = re.search(r'NAME\s+"([^"]+)"', content, re.IGNORECASE)
    macro_match = re.search(r"MACRO\s+WORKSPACE_NAME\s+(\S+)", content, re.IGNORECASE)
    if title_match:
        name = title_match.group(1)
    elif macro_match:
        name = macro_match.group(1)

    nodes: List[dict] = []
    edges: List[dict] = []
    warnings: List[str] = []
    positions_from_source = False

    wb_nodes, wb_edges, _, wb_warnings = _parse_workbench_gui(content, catalog)
    map_nodes, map_edges, name_to_gix, map_warnings = _parse_mapping_factories(content, catalog)

    if wb_nodes:
        nodes, edges = wb_nodes, wb_edges
        warnings.extend(wb_warnings)
        positions_from_source = True
        if not edges and name_to_gix:
            edges = _infer_mapping_edges(content, name_to_gix)
    elif map_nodes:
        nodes, edges = map_nodes, map_edges
        warnings.extend(map_warnings)
        positions_from_source = any(
            re.search(r"X_COORDINATE\s+-?\d", content, re.IGNORECASE) is not None
        )
        if not edges:
            edges = _infer_mapping_edges(content, name_to_gix)
    else:
        warnings.extend(wb_warnings)
        warnings.extend(map_warnings)

    if not nodes:
        xml = _extract_workspace_xml(content)
        if xml:
            try:
                nodes, edges, xml_warnings = _parse_workspace_xml(xml, catalog)
                warnings.extend(xml_warnings)
                positions_from_source = True
            except ET.ParseError as exc:
                warnings.append(f"XML workspace invalide: {exc}")

    if not nodes:
        raise ValueError(FMW_ENCRYPTED_HINT)

    if text_format == "json":
        warnings.append(
            "Format JSON Workbench détecté — import partiel ; préférez un .fmw XML exporté depuis l'éditeur d'origine.",
        )

    if positions_from_source:
        _normalize_canvas_positions(nodes)
    else:
        _layout_hierarchical(nodes, edges)

    if not edges and len(nodes) > 1:
        warnings.append("Aucune connexion workspace détectée — vérifiez FEAT_LINK / ROUTED_TO.")

    return {
        "name": name,
        "format": "4gix_dag",
        "source": "fme_fmw",
        "fme_format": text_format,
        "execution_engine": "4gix_native",
        "warnings": warnings,
        "definition": {"nodes": nodes, "edges": edges},
    }


def _decode_variants(raw: bytes) -> List[str]:
    variants: List[str] = []
    seen: Set[str] = set()

    def add(text: Optional[str]) -> None:
        if not text:
            return
        norm = _normalize_fmw_text(text)
        if norm in seen or len(norm) < 32:
            return
        seen.add(norm)
        variants.append(norm)

    add(extract_embedded_workbench_text(raw))
    add(decode_fmw_bytes(raw))
    add(raw.decode("latin-1", errors="ignore"))
    if raw.startswith(b"\xff\xfe"):
        add(raw.decode("utf-16-le", errors="ignore"))
    loose = _loose_binary_text(raw)
    if loose:
        add(loose)
    for inflated in _inflate_embedded_text(raw):
        add(inflated)
    return variants


def _extract_printable_runs(raw: bytes, *, min_run: int = 6) -> str:
    parts: List[str] = []
    current: List[str] = []
    for byte in raw:
        if 32 <= byte < 127 or byte in (9, 10, 13):
            current.append(chr(byte))
        else:
            if len(current) >= min_run:
                parts.append("".join(current))
            current = []
    if len(current) >= min_run:
        parts.append("".join(current))
    return "\n".join(parts)


def _extract_utf16le_strings(raw: bytes, *, min_chars: int = 4) -> List[str]:
    results: List[str] = []
    index = 0
    limit = len(raw)
    while index < limit - 3:
        if raw[index + 1] != 0 or raw[index] < 32 or raw[index] >= 127:
            index += 1
            continue
        start = index
        chars: List[str] = []
        while index < limit - 1 and raw[index + 1] == 0 and 32 <= raw[index] < 127:
            chars.append(chr(raw[index]))
            index += 2
        if len(chars) >= min_chars:
            results.append("".join(chars))
        else:
            index = start + 2
    return results


def _loose_binary_text(raw: bytes) -> str:
    chunks: List[str] = []
    chunks.append(_extract_printable_runs(raw, min_run=3))
    chunks.extend(_extract_utf16le_strings(raw, min_chars=3))
    return "\n".join(part for part in chunks if part)


def _binary_dictionary_terms() -> List[str]:
    terms: Set[str] = set(NODE_TO_FMW_FACTORY.values())
    terms.update(
        name
        for name in FMW_FACTORY_TO_NODE.keys()
        if len(name) >= 5 and name.isascii()
    )
    terms.update(
        {
            "GeometryValidator",
            "AttributeManager",
            "PostGISWriter",
            "PostGISReader",
            "OGRGeoJSON",
            "ShapefileReader",
            "CSVReader",
            "HTTPCaller",
            "CoordinateSystemSetter",
            "JSONExtractor",
            "FeatureMerger",
            "SpatialRelator",
            "Reprojector",
            "Tester",
            "LogWriter",
        }
    )
    return sorted((t for t in terms if 4 <= len(t) <= 64), key=len, reverse=True)


def _extract_labels_after_wide_marker(raw: bytes, marker: str) -> List[str]:
    wide = b"".join(bytes([byte, 0]) for byte in marker.encode("ascii"))
    labels: List[str] = []
    start = 0
    while True:
        idx = raw.find(wide, start)
        if idx < 0:
            break
        pos = idx + len(wide)
        while pos < len(raw) - 1 and raw[pos] in (0x20, 0x09) and raw[pos + 1] == 0:
            pos += 2
        if pos >= len(raw) - 1 or not (raw[pos] == 0x22 and raw[pos + 1] == 0):
            start = idx + 2
            continue
        pos += 2
        chars: List[str] = []
        while pos < len(raw) - 1:
            if raw[pos] == 0x22 and raw[pos + 1] == 0:
                break
            if raw[pos + 1] != 0 or raw[pos] < 32:
                chars = []
                break
            chars.append(chr(raw[pos]))
            pos += 2
        else:
            chars = []
        if len(chars) >= 2:
            labels.append("".join(chars))
        start = idx + len(wide)
    return labels


def _scan_raw_binary_labels(raw: bytes) -> List[Tuple[str, str]]:
    """Repère des libellés factory directement dans les octets (ASCII + UTF-16)."""
    found: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def push(label: str, fme_type: str) -> None:
        clean = _sanitize_label(label, fallback=fme_type)
        key = _normalize_fme_type(clean)
        if len(key) < 3 or key in seen:
            return
        seen.add(key)
        found.append((clean, fme_type or clean))

    ascii_patterns = (
        rb'FACTORY_NAME\s+"([^"\x00]{2,120})"',
        rb'INSTANCENAME\s*=\s*"([^"\x00]{2,120})"',
        rb'TYPE\s*=\s*"([^"\x00]{2,120})"',
        rb'PARM_VALUE\s*=\s*"([^"\x00]{2,120})"',
        rb'XFORMER_NAME[^"]*"([^"\x00]{2,120})"',
    )
    for pattern in ascii_patterns:
        for match in re.finditer(pattern, raw, flags=re.IGNORECASE):
            label = match.group(1).decode("utf-8", errors="ignore").strip()
            if label:
                push(label, label)

    for marker in ("FACTORY_NAME", "INSTANCENAME", "XFORMER_NAME"):
        for label in _extract_labels_after_wide_marker(raw, marker):
            push(label, label)

    lower_raw = raw.lower()
    for term in _binary_dictionary_terms():
        ascii_needle = term.encode("ascii", errors="ignore")
        if not ascii_needle:
            continue
        if ascii_needle in lower_raw or ascii_needle in raw:
            push(term, term)
            continue
        wide = b"".join(bytes([byte, 0]) for byte in ascii_needle)
        if wide in raw:
            push(term, term)

    return found


def _inflate_embedded_text(raw: bytes) -> List[str]:
    """Tente zlib/gzip sur des fenêtres du fichier (sections parfois compressées)."""
    texts: List[str] = []
    limit = min(len(raw), 4_000_000)
    step = 8192
    for offset in range(0, limit, step):
        window = raw[offset : offset + 600_000]
        for wbits in (15, -15, 31):
            try:
                inflated = zlib.decompress(window, wbits)
            except zlib.error:
                continue
            if b"FACTORY" not in inflated and b"TRANSFORMER" not in inflated:
                continue
            text = inflated.decode("utf-8", errors="ignore")
            if len(text) > 64:
                texts.append(text)
    return texts


def _nodes_from_binary_scan(
    raw: bytes,
    catalog: Dict[str, dict],
) -> Tuple[List[dict], List[dict], List[str]]:
    warnings: List[str] = [
        "Signatures factory détectées dans le binaire (scan octets) — graphe approximatif.",
    ]
    nodes: List[dict] = []
    used_ids: Set[str] = set()
    labels = _scan_raw_binary_labels(raw)
    for label, fme_type in labels:
        node_type = _resolve_node_type(fme_type, label, warnings)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", label)[:36] or node_type
        gix_id = _make_gix_id(node_type, slug, used_ids)
        nodes.append(
            _build_flow_node(
                gix_id,
                node_type,
                label,
                (120.0, 120.0),
                catalog,
                fme_source_type=fme_type,
            )
        )
    edges: List[dict] = []
    if len(nodes) > 1:
        warnings.append(
            "Connexions non déchiffrées — enchaînement séquentiel provisoire.",
        )
        for index in range(len(nodes) - 1):
            src = nodes[index]["id"]
            tgt = nodes[index + 1]["id"]
            edges.append(
                {
                    "id": f"e-bin-{src}-{tgt}",
                    "source": src,
                    "target": tgt,
                    "sourceHandle": "output",
                    "targetHandle": "input",
                    "animated": True,
                }
            )
    return nodes, edges, warnings


def _is_likely_encrypted_fmw(raw: bytes) -> bool:
    head = raw[:512]
    if head.startswith(b"FMW0001") or b"FMW0001" in head:
        return True
    return detect_fmw_binary_format(raw) == "binary_encrypted"


def _skeleton_pipeline_from_name(
    workbench_name: str,
    catalog: Dict[str, dict],
) -> Tuple[List[dict], List[dict], List[str]]:
    warnings = [
        "FMW0001 / workspace chiffré — contenu illisible sans outil propriétaire. "
        "Squelette ETL 4GIx créé à partir du nom du fichier : complétez sources, "
        "paramètres et liens puis « Execute workflow (4GIx) ».",
    ]
    lower = workbench_name.lower()
    specs: List[Tuple[str, str]] = []
    if re.search(r"lidar|las|point.?cloud|dem", lower):
        specs.append(("file_reader", f"{workbench_name} — entrée Lidar/fichier"))
    elif re.search(r"download|http|url|rest|wfs", lower):
        specs.append(("rest_wfs_reader", f"{workbench_name} — source HTTP/WFS"))
    elif re.search(r"geojson|json", lower):
        specs.append(("geojson_reader", f"{workbench_name} — GeoJSON"))
    elif re.search(r"shape|shp", lower):
        specs.append(("file_reader", f"{workbench_name} — Shapefile"))
    else:
        specs.append(("file_reader", f"{workbench_name} — source"))

    specs.append(("attribute_manager", "Transformations (à ajuster)"))
    if re.search(r"postgis|postgres|pg|sql", lower):
        specs.append(("postgis_writer", "PostgreSQL / PostGIS"))
    else:
        specs.append(("file_writer", "Sortie fichier"))

    nodes: List[dict] = []
    edges: List[dict] = []
    used_ids: Set[str] = set()
    for index, (node_type, label) in enumerate(specs):
        if node_type not in NODE_REGISTRY:
            node_type = FALLBACK_NODE_TYPE
        gix_id = _make_gix_id(node_type, str(index), used_ids)
        nodes.append(
            _build_flow_node(
                gix_id,
                node_type,
                label,
                (120.0, 120.0),
                catalog,
            )
        )
    for index in range(len(nodes) - 1):
        edges.append(
            {
                "id": f"e-sk-{index}",
                "source": nodes[index]["id"],
                "target": nodes[index + 1]["id"],
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            }
        )
    _layout_hierarchical(nodes, edges)
    return nodes, edges, warnings


def _parse_loose_fme_signatures(
    text: str,
    catalog: Dict[str, dict],
) -> Tuple[List[dict], List[dict], List[str]]:
    """Heuristique sur texte reconstruit depuis un .fmw binaire (sans déchiffrement propriétaire)."""
    warnings: List[str] = [
        "Fichier .fmw binaire — graphe reconstruit par heuristique ; vérifiez nœuds et liens, "
        "puis « Execute workflow (4GIx) ».",
    ]
    nodes: List[dict] = []
    used_ids: Set[str] = set()
    seen_keys: Set[str] = set()

    def add_node(label: str, fme_type: str, pos: Optional[Tuple[float, float]] = None) -> None:
        safe_label = _sanitize_label(label, fallback=fme_type)
        key = _normalize_fme_type(f"{safe_label}{fme_type}")
        if key in seen_keys:
            return
        seen_keys.add(key)
        node_type = _resolve_node_type(fme_type, safe_label, warnings)
        position = pos if pos else (120.0, 120.0)
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", safe_label)[:36] or node_type
        gix_id = _make_gix_id(node_type, slug, used_ids)
        nodes.append(
            _build_flow_node(
                gix_id,
                node_type,
                safe_label,
                position,
                catalog,
                fme_source_type=fme_type,
            )
        )

    for match in re.finditer(
        r'INSTANCENAME="([^"]{2,120})"[^>]*TYPE="([^"]{2,120})"',
        text,
        re.IGNORECASE,
    ):
        add_node(html.unescape(match.group(1)), html.unescape(match.group(2)))

    for match in re.finditer(
        r'TYPE="([^"]{2,120})"[^>]*INSTANCENAME="([^"]{2,120})"',
        text,
        re.IGNORECASE,
    ):
        add_node(html.unescape(match.group(2)), html.unescape(match.group(1)))

    for match in re.finditer(r'FACTORY_NAME\s+"([^"]{2,120})"', text, re.IGNORECASE):
        fname = html.unescape(match.group(1))
        window = text[match.start() : match.start() + 2500]
        def_match = re.search(r"FACTORY_DEF\s+\S+\s+(\w+)", window, re.IGNORECASE)
        factory_class = (def_match.group(1) if def_match else "").lower()
        type_hint = FACTORY_CLASS_HINT.get(factory_class) or factory_class.replace("factory", "")
        add_node(fname, type_hint or factory_class or fname)

    for match in re.finditer(
        r'PARM_NAME="XFORMER_NAME"\s+PARM_VALUE="([^"]{2,120})"',
        text,
        re.IGNORECASE,
    ):
        label = html.unescape(match.group(1))
        window = text[max(0, match.start() - 800) : match.start() + 800]
        type_match = re.search(r'TYPE="([^"]+)"', window, re.IGNORECASE)
        fme_type = html.unescape(type_match.group(1)) if type_match else label
        add_node(label, fme_type)

    for match in re.finditer(
        r"\b([\w][\w .-]{1,48}(?:Reader|Writer|Transformer|Clipper|Dissolver|Bufferer))\b",
        text,
        re.IGNORECASE,
    ):
        token = match.group(1).strip()
        if token.lower() in {"feature type", "output feature"}:
            continue
        add_node(token, token)

    edges: List[dict] = []
    if len(nodes) > 1:
        warnings.append(
            "Connexions non lisibles dans le binaire — enchaînement séquentiel provisoire.",
        )
        for index in range(len(nodes) - 1):
            src = nodes[index]["id"]
            tgt = nodes[index + 1]["id"]
            edges.append(
                {
                    "id": f"e-seq-{src}-{tgt}",
                    "source": src,
                    "target": tgt,
                    "sourceHandle": "output",
                    "targetHandle": "input",
                    "animated": True,
                }
            )
    return nodes, edges, warnings


def _recover_fmw_from_binary(
    raw: bytes,
    *,
    default_name: str,
) -> Optional[Dict[str, Any]]:
    catalog = _catalog_index()
    loose = _loose_binary_text(raw)
    nodes, edges, warnings = _nodes_from_binary_scan(raw, catalog)
    if not nodes and len(loose.strip()) >= 16:
        nodes, edges, warnings = _parse_loose_fme_signatures(loose, catalog)
    if not nodes:
        map_nodes, map_edges, name_to_gix, map_warnings = _parse_mapping_factories(
            loose,
            catalog,
        )
        if map_nodes:
            nodes, edges = map_nodes, map_edges
            warnings = list(map_warnings)
            warnings.insert(
                0,
                "Section mapping détectée dans le binaire — graphe approximatif pour ETL 4GIx.",
            )
            if not edges and name_to_gix:
                edges = _infer_mapping_edges(loose, name_to_gix)
        elif _is_likely_encrypted_fmw(raw) and len(raw) >= 256:
            nodes, edges, warnings = _skeleton_pipeline_from_name(default_name, catalog)
        else:
            return None
    if not nodes:
        return None
    _layout_hierarchical(nodes, edges)
    intro = (
        "Graphe approximé pour le moteur ETL 4GIx (aucun moteur externe requis à l'exécution)."
    )
    return {
        "name": default_name,
        "format": "4gix_dag",
        "source": "fme_fmw_binary_heuristic",
        "fme_format": detect_fmw_binary_format(raw),
        "execution_engine": "4gix_native",
        "warnings": [intro, *warnings],
        "definition": {"nodes": nodes, "edges": edges},
    }


def parse_fmw_bytes(raw: bytes, *, default_name: str = "Import .fmw") -> Dict[str, Any]:
    """Import multi-stratégies sans moteur externe — graphe approximé pour ETL 4GIx."""
    if not raw:
        raise ValueError("Fichier vide.")
    intro = (
        "Graphe approximé pour le moteur ETL 4GIx (aucun moteur externe requis à l'exécution)."
    )
    last_error: Optional[ValueError] = None
    for text in _decode_variants(raw):
        try:
            payload = parse_fmw(text, default_name=default_name)
        except ValueError as exc:
            last_error = exc
            continue
        nodes = payload.get("definition", {}).get("nodes") or []
        if not nodes:
            continue
        warnings = list(payload.get("warnings") or [])
        if intro not in warnings:
            warnings.insert(0, intro)
        payload["warnings"] = warnings
        payload["execution_engine"] = "4gix_native"
        return payload
    recovered = _recover_fmw_from_binary(raw, default_name=default_name)
    if recovered:
        return recovered
    if len(raw) >= 128:
        catalog = _catalog_index()
        nodes, edges, warnings = _skeleton_pipeline_from_name(default_name, catalog)
        intro = (
            "Graphe approximé pour le moteur ETL 4GIx (aucun moteur externe requis à l'exécution)."
        )
        return {
            "name": default_name,
            "format": "4gix_dag",
            "source": "fme_fmw_skeleton",
            "fme_format": detect_fmw_binary_format(raw),
            "execution_engine": "4gix_native",
            "warnings": [intro, *warnings],
            "definition": {"nodes": nodes, "edges": edges},
        }
    raise last_error or ValueError(FMW_ENCRYPTED_HINT)


def export_fmw(definition: Dict[str, Any], name: str = "4GIx Export") -> str:
    nodes = definition.get("nodes") or []
    edges = definition.get("edges") or []
    lines = [
        "#! 4GIx FMW Workspace",
        "#! Exported by 4GIx Recflow",
        f'#! NAME "{name}"',
        '#! <WORKSPACE FORMAT="1.0" ENCODING="UTF-8">',
        "#!   <TRANSFORMER_LIST>",
    ]
    id_rev: Dict[str, str] = {}
    for index, node in enumerate(nodes, start=1):
        data = node.get("data") or {}
        node_type = data.get("nodeType") or node.get("type") or "transformer"
        fme_type = NODE_TO_FMW_FACTORY.get(node_type, node_type)
        fid = str(index)
        nid = node.get("id") or fid
        id_rev[nid] = fid
        pos = node.get("position") or {}
        x = pos.get("x", 100)
        y = pos.get("y", 100)
        label = _sanitize_label(data.get("label"), fallback=fme_type)
        lines.append(
            f'#!     <TRANSFORMER IDENTIFIER="{fid}" INSTANCENAME="{label}" '
            f'TYPE="{fme_type}" POSITION="{x},{y}"/>'
        )
    lines.append("#!   </TRANSFORMER_LIST>")
    lines.append("#!   <LINK_LIST>")
    for edge in edges:
        src = id_rev.get(edge.get("source"), edge.get("source"))
        tgt = id_rev.get(edge.get("target"), edge.get("target"))
        if not src or not tgt:
            continue
        sport = (edge.get("sourceHandle") or "output").upper()
        tport = (edge.get("targetHandle") or "input").upper()
        lines.append(
            f'#!     <LINK SOURCE="{src}" SOURCE_PORT="{sport}" '
            f'TARGET="{tgt}" TARGET_PORT="{tport}"/>'
        )
    lines.append("#!   </LINK_LIST>")
    lines.append("#! </WORKSPACE>")
    lines.append("")
    lines.append("# Mapping file stub (regenerated by un éditeur .fmw externe à l'ouverture)")
    lines.append(f"# 4GIx workflow: {name}")
    lines.append(f"# nodes={len(nodes)} edges={len(edges)}")
    return "\n".join(lines)
