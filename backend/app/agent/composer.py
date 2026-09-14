"""Planificateur Composer : thoughts, tool calls et diffs de code."""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from app.core.crs import normalize_crs

from app.agent.geometry_healing import (
    build_proactive_suggestions,
    enrich_inspect_geometry_flags,
    geometry_heal_step_config,
    is_spatial_writer,
    resolve_spatial_export_writer,
)
from app.agent.tools import (
    execute_tool,
    graph_edges,
    graph_nodes,
    node_type_of,
    tool_call_summary,
)

COMPOSER_STEP_OFFSET_X = 280.0
COMPOSER_BRANCH_OFFSET_Y = 150.0

_FILTER_RE = re.compile(
    r"(?:filtre(?:r)?|filter)(?:\s+la)?(?:\s+colonne|\s+column)?\s*['\"]?(?P<field>[A-Za-z_][\w]*)['\"]?"
    r"\s*(?P<op>>=|<=|>|<|==|=)\s*['\"]?(?P<value>-?\d+(?:[.,]\d+)?)['\"]?",
    re.IGNORECASE,
)
_SIMPLE_FILTER_RE = re.compile(
    r"['\"](?P<field>[A-Za-z_][\w]*)['\"]\s*(?P<op>>=|<=|>|<|==|=)\s*(?P<value>-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_NATURAL_SUPERIOR_RE = re.compile(
    r"(?:superieur(?:e)?s?|supérieur(?:e)?s?)\s+(?:à|a)\s*"
    r"(?P<value>-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_NATURAL_INFERIOR_RE = re.compile(
    r"(?:inferieur(?:e)?s?|inférieur(?:e)?s?)\s+(?:à|a)\s*"
    r"(?P<value>-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_FIELD_HINT_RE = re.compile(
    r"(?:\bsur\b|\bcolonne\b|\bchamp\b)\s+(?P<hint>.+?)"
    r"(?:\s+les?\b|\s+où\b|\s+where\b|\s+superieur|\s+supérieur|\s+inferieur|\s+inférieur|\s*[><=])",
    re.IGNORECASE,
)
_FILTER_INTENT_RE = re.compile(
    r"\b(?:filtre(?:r)?|filter|superieur|supérieur|inferieur|inférieur|>|>=|<|<=|=)\b",
    re.IGNORECASE,
)


def _normalize_field_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _fuzzy_match_column(hint: str, columns: Iterable[str]) -> Optional[str]:
    cols = [str(c) for c in columns if str(c).strip()]
    if not cols or not hint.strip():
        return None
    hint_norm = _normalize_field_token(hint)
    if not hint_norm:
        return None
    hint_words = [
        _normalize_field_token(w)
        for w in re.split(r"\s+", hint.strip())
        if len(w.strip()) > 2
    ]
    best_score = 0.0
    best_col: Optional[str] = None
    for col in cols:
        col_norm = _normalize_field_token(col)
        if not col_norm:
            continue
        if col_norm == hint_norm:
            return col
        ratio = difflib.SequenceMatcher(None, hint_norm, col_norm).ratio()
        word_bonus = sum(
            0.12 for word in hint_words if word and word in col_norm
        )
        ratio = min(1.0, ratio + min(word_bonus, 0.48))
        if hint_norm in col_norm or col_norm in hint_norm:
            ratio = max(ratio, 0.9)
        if ratio > best_score:
            best_score = ratio
            best_col = col
    if best_col and best_score >= 0.42:
        return best_col
    return None


def _map_operator(op_raw: str) -> str:
    op_map = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "=": "eq", "==": "eq"}
    key = op_raw.lower()
    return op_map.get(key, key if key in {"gt", "lt", "eq", "gte", "lte"} else "gt")


def _extract_natural_filter(text: str) -> Optional[Dict[str, str]]:
    if not _FILTER_INTENT_RE.search(text):
        return None
    value: Optional[str] = None
    operator = "gt"
    sup = _NATURAL_SUPERIOR_RE.search(text)
    inf = _NATURAL_INFERIOR_RE.search(text)
    sym = re.search(r"(?P<op>>=|<=|>|<|==|=)\s*['\"]?(-?\d+(?:[.,]\d+)?)", text)
    if sup:
        value = sup.group("value").replace(",", ".")
        operator = "gt"
    elif inf:
        value = inf.group("value").replace(",", ".")
        operator = "lt"
    elif sym:
        value = sym.group(2).replace(",", ".")
        operator = _map_operator(sym.group("op"))
    else:
        trailing = re.search(
            r"(?:>|>=|<|<=|=)\s*(-?\d+(?:[.,]\d+)?)\s*$",
            text.strip(),
        )
        if trailing:
            value = trailing.group(1).replace(",", ".")
        else:
            last_num = re.findall(r"(-?\d+(?:[.,]\d+)?)", text)
            if last_num:
                value = last_num[-1].replace(",", ".")
    if value is None:
        return None

    field_hint = ""
    hint_match = _FIELD_HINT_RE.search(text)
    if hint_match:
        field_hint = hint_match.group("hint").strip()
    else:
        tokens = re.findall(r"[A-Za-zÀ-ÿ_][\wÀ-ÿ]*", text, re.UNICODE)
        stop = {
            "filtre",
            "filter",
            "moi",
            "sur",
            "les",
            "le",
            "la",
            "puissance",
            "superieur",
            "supérieur",
            "inferieur",
            "inférieur",
            "a",
            "à",
            "estime",
            "source",
        }
        kept = [t for t in tokens if t.lower() not in stop and not t.isdigit()]
        if kept:
            field_hint = " ".join(kept[:6])

    if not field_hint:
        field_hint = "value"
    return {"field": field_hint, "operator": operator, "value": value}


def wants_filter_intent(prompt: str) -> bool:
    return bool(_FILTER_INTENT_RE.search(prompt or ""))


_SOURCE_TYPE_INTENT_RE = re.compile(
    r"\b(?:filtre(?:r)?|filter|type\s*de\s*source|type\s*source|\bled\b)",
    re.IGNORECASE,
)


def _pick_type_source_column(columns: Iterable[str]) -> Optional[str]:
    cols = [str(c) for c in columns if str(c).strip()]
    if not cols:
        return None
    ranked: List[tuple[int, str]] = []
    for col in cols:
        norm = _normalize_field_token(col)
        upper = col.upper()
        score = 0
        if norm in {"typesource", "typesources", "typesrc"}:
            score = 100
        elif "TYPE" in upper and "SOURCE" in upper:
            score = 90
        elif "type" in norm and "source" in norm:
            score = 85
        elif "TYPE" in upper and "SUPPORT" in upper:
            score = 70
        elif "type" in norm and "support" in norm:
            score = 65
        elif "type" in norm:
            score = 40
        if score:
            ranked.append((score, col))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def parse_source_type_filter(
    prompt: str,
    columns: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, str]]:
    """Fallback : filtre « type de source » / LED sur colonnes TYPE_SOURCE etc."""
    text = prompt or ""
    if not _SOURCE_TYPE_INTENT_RE.search(text):
        return None
    col_list = list(columns or [])
    field = _pick_type_source_column(col_list)
    if not field and re.search(r"type\s*(?:de\s*)?source", text, re.IGNORECASE):
        for candidate in ("TYPE_SOURCE", "TYPE_SUPPORT", "TYPE_SRC"):
            if not col_list or candidate in col_list:
                field = candidate if candidate in col_list else (
                    _pick_type_source_column([candidate]) or candidate
                )
                break
        if not field:
            field = "TYPE_SOURCE"
    if not field:
        return None
    lower = text.lower()
    value = "LED" if re.search(r"\bled\b", lower) else ""
    if not value:
        token_match = re.search(
            r"\bles?\s+([a-zA-ZÀ-ÿ0-9_\-]+)",
            text,
            re.IGNORECASE,
        )
        if token_match:
            value = token_match.group(1).strip().upper()
    if not value:
        value = "LED"
    return {"field": field, "operator": "contains", "value": value}


def resolve_filter_spec(
    prompt: str,
    columns: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, str]]:
    return parse_attribute_filter(prompt, columns) or parse_source_type_filter(
        prompt, columns
    )


_MULTI_FILTER_SPLIT_RE = re.compile(
    r"\s+(?:"
    r"et\s+un\s+autre(?:\s+filtre(?:r)?)?"
    r"|et\s+aussi(?:\s+(?:un\s+)?filtre(?:r)?)?"
    r"|ainsi\s+que(?:\s+(?:un\s+)?filtre(?:r)?)?"
    r"|puis(?:\s+(?:un\s+)?filtre(?:r)?)?"
    r"|et\s+un\s+filtre(?:r)?"
    r")\b",
    re.IGNORECASE,
)
_STOP_VALUE_WORDS = {
    "filtre",
    "filter",
    "sur",
    "le",
    "la",
    "les",
    "un",
    "une",
    "de",
    "du",
    "des",
    "je",
    "veux",
    "moi",
    "fait",
    "faire",
    "et",
    "puis",
    "ainsi",
    "autre",
    "genere",
    "génère",
    "generer",
    "générer",
    "exporte",
    "export",
    "shp",
    "shapefile",
    "fichier",
}
_FILTER_VALUE_TAIL_RE = re.compile(
    r"\s+(?:"
    r"et(?:\s+(?:un|une|fait|faire|gen[eè]re(?:r)?|exporte(?:r)?|moi|de\s+son\s+c[ôo]t[ée]))?"
    r"|puis(?:\s+(?:un|une|fait|faire|gen[eè]re(?:r)?))?"
    r"|ainsi\s+que"
    r"|et\s+un\s+autre"
    r").*$",
    re.IGNORECASE,
)


def _normalize_filter_value(raw: str) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip(" \t\"'"))
    text = _FILTER_VALUE_TAIL_RE.sub("", text).strip(" \t\"'.,;")
    return text.upper()


def _words_as_filter_value(text: str) -> Optional[str]:
    words: List[str] = []
    for word in re.findall(r"[A-Za-zÀ-ÿ0-9]+", text or ""):
        if word.lower() in _STOP_VALUE_WORDS:
            if words:
                break
            continue
        words.append(word.upper())
        if len(words) >= 4:
            break
    if not words:
        return None
    value = " ".join(words)
    if value in {"CSV", "SHP", "GEOJSON", "GPKG", "CC43", "ANALYSE", "ANALYSER"}:
        return None
    return value


def _contains_value_from_segment(segment: str) -> Optional[str]:
    text = segment or ""
    typed = re.search(
        r"type\s*(?:de\s*)?source\s+['\"]?(.+)$",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if typed:
        tail = re.split(
            _MULTI_FILTER_SPLIT_RE,
            typed.group(1),
            maxsplit=1,
        )[0]
        value = _words_as_filter_value(tail)
        if value:
            return value
    match = re.search(
        r"(?:que\s+les?\s+|les?\s+|sur\s+)([a-zA-ZÀ-ÿ][\w À-ÿ-]{0,48})",
        text,
        re.IGNORECASE,
    )
    if match:
        raw = re.split(r"\b(?:et|puis|ainsi)\b", match.group(1), maxsplit=1)[0]
        value = _words_as_filter_value(raw)
        if value:
            return value
    phrase = re.search(r"\b(lampe\s+led|led)\b", text, re.IGNORECASE)
    if phrase:
        return _normalize_filter_value(phrase.group(1))
    return None


def _split_filter_clauses(text: str) -> List[str]:
    parts = [p.strip() for p in _MULTI_FILTER_SPLIT_RE.split(text or "") if p.strip()]
    if len(parts) >= 2:
        return parts
    hits = list(re.finditer(r"\bfiltre(?:r)?s?\b", text or "", re.IGNORECASE))
    if len(hits) >= 2:
        clauses: List[str] = []
        for index, match in enumerate(hits):
            end = hits[index + 1].start() if index + 1 < len(hits) else len(text)
            clauses.append(text[match.start() : end].strip())
        return [c for c in clauses if c]
    return [text] if text.strip() else []


def _type_source_values(text: str) -> List[str]:
    values: List[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"type\s*(?:de\s*)?source\s+", text or "", re.IGNORECASE):
        rest = (text or "")[match.end() :]
        rest = _MULTI_FILTER_SPLIT_RE.split(rest, maxsplit=1)[0]
        value = _words_as_filter_value(rest)
        if not value or value in seen:
            continue
        seen.add(value)
        values.append(value)
    if len(values) < 2:
        for match in re.finditer(r"\b(lampe\s+led|led)\b", text or "", re.IGNORECASE):
            value = _normalize_filter_value(match.group(1))
            if value not in seen:
                seen.add(value)
                values.append(value)
    return values


def parse_multiple_filter_specs(
    prompt: str,
    columns: Optional[Iterable[str]] = None,
) -> List[Dict[str, str]]:
    """Découpe chaque critère de filtre en une spec distincte (jamais fusionnés)."""
    text = prompt or ""
    col_list = list(columns or [])
    field = _pick_type_source_column(col_list) or "TYPE_SOURCE"
    specs: List[Dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def _push(value: str, operator: str = "contains") -> None:
        cleaned = _normalize_filter_value(value)
        if not cleaned:
            return
        key = (field.upper(), operator, cleaned)
        if key in seen:
            return
        seen.add(key)
        specs.append({"field": field, "operator": operator, "value": cleaned})

    for value in _type_source_values(text):
        _push(value)

    if len(specs) < 2:
        for part in _split_filter_clauses(text):
            spec = resolve_filter_spec(part, col_list)
            value = _contains_value_from_segment(part)
            if value:
                _push(value, "contains")
            elif spec:
                _push(str(spec.get("value") or ""), spec.get("operator") or "contains")

    if not specs:
        single = resolve_filter_spec(text, col_list)
        if single:
            return [single]
    return specs


_BRANCH_OBJECTIVE_SPLIT_RE = re.compile(
    r"\s+(?:"
    r"et\s+un\s+autre(?:\s+filtre(?:r)?)?"
    r"|et\s+de\s+son\s+c[ôo]t[ée]"
    r"|d['\u2019]un\s+autre\s+c[ôo]t[ée]"
    r"|et\s+aussi(?:\s+(?:un\s+)?filtre(?:r)?)?"
    r"|ainsi\s+que(?:\s+(?:un\s+)?filtre(?:r)?)?"
    r"|et\s+un\s+filtre(?:r)?"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class ParallelBranchObjective:
    """Sous-objectif indépendant (filtre + export éventuel) depuis la source."""

    text: str
    filter_spec: Optional[Dict[str, str]]
    writer_type: Optional[str]


def _clause_for_filter_parse(clause: str) -> str:
    """Retire la partie export (« et génère un shp ») avant d'extraire la valeur filtre."""
    text = (clause or "").strip()
    export_cut = re.search(
        r"\b(?:"
        r"et\s+(?:fait(?:\s+moi)?|faire)|"
        r"(?:et\s+)?(?:"
        r"gen[eè]re(?:r)?|exporte(?:r)?|cr[eé]e(?:r)?|sauve(?:r|garde)?|"
        r"enregistre(?:r)?|produi(?:s|t|re)|fabrique(?:r)?"
        r")"
        r")(?:\s+moi)?(?:\s+(?:un|une|le|la))?\s*(?:"
        r"shp|shapefile|geojson|gpkg|geopackage|csv|fichier"
        r")?\b",
        text,
        re.IGNORECASE,
    )
    if export_cut:
        return text[: export_cut.start()].strip(" ,.;")
    branch_cut = _BRANCH_OBJECTIVE_SPLIT_RE.search(text)
    if branch_cut:
        return text[: branch_cut.start()].strip(" ,.;")
    return text


def _filter_spec_for_clause(clause: str, columns: List[str]) -> Optional[Dict[str, str]]:
    cleaned = _clause_for_filter_parse(clause)
    col_list = list(columns or [])
    field = _pick_type_source_column(col_list) or "TYPE_SOURCE"
    value = _contains_value_from_segment(cleaned)
    if value:
        return {"field": field, "operator": "contains", "value": value}
    specs = parse_multiple_filter_specs(cleaned, columns)
    if specs:
        return specs[0]
    return resolve_filter_spec(cleaned, columns)


def parse_parallel_branch_objectives(
    prompt: str,
    columns: Optional[Iterable[str]] = None,
) -> List[ParallelBranchObjective]:
    """Découpe en branches parallèles (chaque branche repart de la source)."""
    text = (prompt or "").strip()
    if not text:
        return []
    col_list = list(columns or [])
    parts = [
        p.strip()
        for p in _BRANCH_OBJECTIVE_SPLIT_RE.split(text)
        if p and p.strip()
    ]
    if len(parts) < 2:
        return []
    branches: List[ParallelBranchObjective] = []
    for index, part in enumerate(parts):
        clause = part
        if index > 0 and not re.search(r"\bfiltre", clause, re.IGNORECASE):
            clause = f"filtre {clause}"
        filter_spec = _filter_spec_for_clause(clause, col_list)
        writer_type = detect_export_writer(clause)
        if filter_spec or writer_type:
            branches.append(
                ParallelBranchObjective(
                    text=clause,
                    filter_spec=filter_spec,
                    writer_type=writer_type,
                )
            )
    return branches if len(branches) >= 2 else []


def parse_attribute_filter(
    prompt: str,
    columns: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, str]]:
    text = prompt or ""
    match = _FILTER_RE.search(text) or _SIMPLE_FILTER_RE.search(text)
    spec: Optional[Dict[str, str]] = None
    if match:
        spec = {
            "field": match.group("field"),
            "operator": _map_operator(match.group("op")),
            "value": match.group("value").replace(",", "."),
        }
    else:
        spec = _extract_natural_filter(text)

    if not spec:
        return None

    col_list = list(columns or [])
    if col_list:
        resolved = _fuzzy_match_column(spec["field"], col_list)
        if resolved:
            spec = {**spec, "field": resolved}
    return spec


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


def wants_mapping_intent(prompt: str) -> bool:
    text = (prompt or "").lower()
    if any(
        token in text
        for token in (
            "mappage",
            "mapping",
            "remap",
            "remapper",
            "attribute mapper",
            "attribute_mapper",
            "attribute mapper",
            "map values",
        )
    ):
        return True
    return "renommer" in text and any(
        token in text for token in ("colonne", "colonnes", "champ", "attribut")
    )


def wants_data_cleaning_intent(prompt: str) -> bool:
    text = (prompt or "").lower()
    return any(
        token in text
        for token in (
            "nettoy",
            "nettoye",
            "clean",
            "doublon",
            "dédoubl",
            "dedup",
            "dedoubl",
        )
    )


def needs_mapping_guidance(prompt: str) -> bool:
    return wants_mapping_intent(prompt) or wants_data_cleaning_intent(prompt)


def column_to_snake(name: str) -> str:
    folded = (
        unicodedata.normalize("NFKD", str(name))
        .encode("ascii", "ignore")
        .decode("ascii")
        .strip()
        .lower()
    )
    folded = re.sub(r"[^\w]+", "_", folded)
    folded = re.sub(r"_+", "_", folded).strip("_")
    return folded or "field"


def mapping_has_explicit_detail(prompt: str, columns: List[str]) -> bool:
    text = prompt or ""
    lower = text.lower()
    if re.search(r"\{[^}]+\}", text):
        return True
    if "->" in text or "→" in text or re.search(r"\bvers\b", lower):
        return True
    if wants_mapping_intent(text) or wants_data_cleaning_intent(text):
        for col in columns:
            if col and col.lower() in lower:
                return True
    return False


def _build_snake_case_mapping(columns: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for col in columns:
        target = column_to_snake(col)
        if target and target != col:
            mapping[col] = target
    return mapping


_CNIG_FIELD_HINTS: Dict[str, tuple[str, ...]] = {
    "id": ("id", "gid", "objectid", "identifiant"),
    "code_insee": ("code_insee", "insee", "code_commune", "code_foyer"),
    "nom": ("nom", "name", "libelle", "libellé", "label"),
    "type": ("type", "type_suppo", "type_support", "typologie"),
    "date_maj": ("date", "maj", "updated", "timestamp"),
}


def _build_cnig_mapping(columns: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for col in columns:
        snake = column_to_snake(col)
        std_name = None
        for std, hints in _CNIG_FIELD_HINTS.items():
            if snake == std or any(h in snake for h in hints):
                std_name = std
                break
        mapping[col] = std_name or snake
    return mapping


_DEDUPE_PYTHON_CODE = (
    "# Nettoyage — colonnes et lignes en double\n"
    "work = gdf.loc[:, ~gdf.columns.duplicated()].copy()\n"
    "return work.drop_duplicates()\n"
)


def build_mapping_choice_options(columns: List[str]) -> List[Dict[str, Any]]:
    if not columns:
        return []
    preview = ", ".join(f"« {name} »" for name in columns[:5])
    if len(columns) > 5:
        preview = f"{preview} (+{len(columns) - 5})"
    snake = _build_snake_case_mapping(columns)
    cnig = _build_cnig_mapping(columns)
    return [
        {
            "id": "snake_case",
            "label": "Option A — Normaliser en snake_case",
            "description": (
                f"Renommer les colonnes ({preview}) en minuscules avec underscores "
                "(ex. code_foyer, type_suppo)."
            ),
            "node_type": "attribute_mapper",
            "config": {
                "mapping": json.dumps(snake, ensure_ascii=False),
                "keep_unmapped": True,
            },
        },
        {
            "id": "dedupe_essential",
            "label": "Option B — Attributs essentiels et dédoublonnage",
            "description": (
                "Supprimer les colonnes dupliquées puis les lignes strictement identiques."
            ),
            "node_type": "python_caller",
            "config": {"language": "python", "code": _DEDUPE_PYTHON_CODE},
        },
        {
            "id": "cnig_covadis",
            "label": "Option C — Modèle SIG (COVADIS / CNIG)",
            "description": (
                "Rapprocher les noms vers des champs standard SIG "
                "(id, code_insee, nom, type, date_maj…)."
            ),
            "node_type": "attribute_mapper",
            "config": {
                "mapping": json.dumps(cnig, ensure_ascii=False),
                "keep_unmapped": True,
            },
        },
    ]


def resolve_mapping_choice(
    choice_id: str, columns: List[str]
) -> Optional[Dict[str, Any]]:
    for option in build_mapping_choice_options(columns):
        if option.get("id") == choice_id:
            return option
    return None


def mapping_step_summary(choice_id: str) -> str:
    labels = {
        "snake_case": "Mappage attributaire — normalisation snake_case",
        "dedupe_essential": "Nettoyage — dédoublonnage colonnes et lignes",
        "cnig_covadis": "Mappage attributaire — modèle COVADIS / CNIG",
    }
    return labels.get(choice_id, "Mappage attributaire")


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


@dataclass
class _ComposerChainStep:
    node_type: str
    config: Dict[str, Any]
    summary: Optional[str] = None


def _branch_y(origin: Dict[str, float], branch_index: int) -> float:
    return origin["y"] + COMPOSER_BRANCH_OFFSET_Y * max(0, branch_index)


def _filter_node_config(filter_spec: Dict[str, str]) -> Dict[str, Any]:
    operator = filter_spec.get("operator") or "contains"
    if str(operator).upper() == "CONTAINS":
        operator = "contains"
    elif operator == "gte":
        operator = "gt"
    return {
        "field": filter_spec["field"],
        "operator": operator,
        "value": filter_spec["value"],
    }


def _composer_append_tool_call(
    events: List[Dict[str, Any]],
    name: str,
    summary: str,
    arguments: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    events.append(
        _event(
            "tool_call",
            name=name,
            summary=summary,
            arguments=arguments,
            result=result,
        )
    )


def _composer_create_node(
    events: List[Dict[str, Any]],
    graph: Dict[str, Any],
    node_type: str,
    position: Dict[str, float],
    config: Dict[str, Any],
    summary: Optional[str] = None,
) -> Dict[str, Any]:
    args = {"node_type": node_type, "position": position, "config": config}
    result = execute_tool("create_canvas_node", args, graph)
    _composer_append_tool_call(
        events,
        "create_canvas_node",
        summary or f"create_node({node_type})",
        args,
        result,
    )
    return result


def _composer_connect(
    events: List[Dict[str, Any]],
    graph: Dict[str, Any],
    from_id: str,
    to_id: str,
) -> Dict[str, Any]:
    args = {
        "from_node_id": from_id,
        "from_port": "output",
        "to_node_id": to_id,
        "to_port": "input",
    }
    result = execute_tool("connect_nodes", args, graph)
    _composer_append_tool_call(events, "connect_nodes", "connect(...)", args, result)
    return result


def _composer_finish(
    events: List[Dict[str, Any]],
    created_ids: Dict[str, str],
    source_id: str,
) -> List[Dict[str, Any]]:
    sequence = [
        item.get("summary")
        for item in events
        if item.get("type") == "tool_call"
        and item.get("name") in {"create_canvas_node", "connect_nodes"}
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


def _emit_mapping_choice_pipeline(
    events: List[Dict[str, Any]],
    graph: Dict[str, Any],
    *,
    source_id: str,
    origin: Dict[str, float],
    choice: Dict[str, Any],
    created_ids: Dict[str, str],
) -> None:
    node_type = str(choice.get("node_type") or "attribute_mapper")
    config = dict(choice.get("config") or {})
    y_offset = COMPOSER_BRANCH_OFFSET_Y if node_type == "python_caller" else 0.0
    position = {
        "x": origin["x"] + COMPOSER_STEP_OFFSET_X,
        "y": origin["y"] + y_offset,
    }
    node = _composer_create_node(
        events,
        graph,
        node_type,
        position,
        config,
        f"create_node({node_type})",
    )
    created_ids[node_type] = node["id"]
    _composer_connect(events, graph, source_id, node["id"])


def _append_mapping_guidance_events(
    events: List[Dict[str, Any]],
    *,
    prompt: str,
    schema_columns: List[str],
) -> None:
    preview = ", ".join(f"« {name} »" for name in schema_columns[:6])
    if len(schema_columns) > 6:
        preview = f"{preview} (+{len(schema_columns) - 6})"
    intro = (
        f"Consigne « {prompt.strip()} » : précisez une stratégie de mappage. "
        f"Colonnes @INPUT : {preview or '—'}.\n\n"
        "Choisissez une option pour générer le nœud Attribute Mapper / Python "
        "et l'insérer dans le DAG."
    )
    options = build_mapping_choice_options(schema_columns)
    events.append(_event("thought", content=intro))
    events.append(_event("mapping_choices", choices=options))


def _export_chain_steps(
    writer_type: str,
    inspect: Dict[str, Any],
) -> tuple[List[_ComposerChainStep], List[str]]:
    enriched = enrich_inspect_geometry_flags(inspect)
    resolved, _, msgs = resolve_spatial_export_writer(writer_type, enriched)
    steps: List[_ComposerChainStep] = []
    if is_spatial_writer(resolved):
        heal_cfg = geometry_heal_step_config(enriched)
        if heal_cfg:
            steps.append(
                _ComposerChainStep(
                    "vertex_creator",
                    heal_cfg,
                    "create_node(vertex_creator)",
                )
            )
    steps.append(
        _ComposerChainStep(resolved, {}, f"create_node({resolved})"),
    )
    return steps, msgs


def _emit_branch_pipeline(
    events: List[Dict[str, Any]],
    graph: Dict[str, Any],
    *,
    source_id: str,
    origin: Dict[str, float],
    branch_index: int,
    filter_spec: Optional[Dict[str, str]],
    writer_type: Optional[str],
    inspect: Dict[str, Any],
    created_ids: Dict[str, str],
) -> None:
    y = _branch_y(origin, branch_index)
    column = 0
    connect_from = source_id

    if filter_spec:
        column += 1
        filter_node = _composer_create_node(
            events,
            graph,
            "attribute_filter",
            {"x": origin["x"] + COMPOSER_STEP_OFFSET_X * column, "y": y},
            _filter_node_config(filter_spec),
        )
        created_ids[f"attribute_filter_{branch_index}"] = filter_node["id"]
        _composer_connect(events, graph, connect_from, filter_node["id"])
        connect_from = filter_node["id"]

    if not writer_type:
        return

    chain_steps, msgs = _export_chain_steps(writer_type, inspect)
    for msg in msgs:
        events.append(_event("thought", content=msg))
    for step in chain_steps:
        column += 1
        node = _composer_create_node(
            events,
            graph,
            step.node_type,
            {"x": origin["x"] + COMPOSER_STEP_OFFSET_X * column, "y": y},
            step.config,
            step.summary,
        )
        created_ids[f"{step.node_type}_{branch_index}"] = node["id"]
        _composer_connect(events, graph, connect_from, node["id"])
        connect_from = node["id"]
        if step.node_type == "python_caller":
            code = str(step.config.get("code") or "")
            code_patch = execute_tool(
                "update_node_code",
                {"node_id": node["id"], "code": code, "language": "python"},
                graph,
            )
            events.append(
                _event(
                    "code_diff",
                    node_id=node["id"],
                    language="python",
                    diff=unified_diff("", code, "transform.py"),
                    code=code,
                    result=code_patch,
                )
            )


def _build_composer_branches(
    prompt: str,
    schema_columns: List[str],
    writer_type: Optional[str],
) -> List[ParallelBranchObjective]:
    parallel = parse_parallel_branch_objectives(prompt, schema_columns)
    if len(parallel) >= 2:
        return parallel
    specs = parse_multiple_filter_specs(prompt, schema_columns)
    if len(specs) > 1:
        return [
            ParallelBranchObjective(
                text="",
                filter_spec=spec,
                writer_type=writer_type,
            )
            for spec in specs
        ]
    return []


def _append_proactive_suggestions(
    events: List[Dict[str, Any]],
    prompt: str,
    inspect: Dict[str, Any],
    step_kinds: List[str],
) -> None:
    for suggestion in build_proactive_suggestions(prompt, inspect, step_kinds):
        events.append(_event("thought", content=f"Suite possible : {suggestion}"))


def plan_composer(
    prompt: str,
    current_graph: Optional[Dict[str, Any]] = None,
    selected_node_id: Optional[str] = None,
    context_mentions: Optional[Iterable[str]] = None,
    source_node_id: Optional[str] = None,
    node_id: Optional[str] = None,
    mapping_choice_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Produit la séquence SSE (thought / tool_call / code_diff)."""
    graph = current_graph or {"nodes": [], "edges": []}
    mentions = [str(item) for item in (context_mentions or [])]
    anchor_id = node_id or selected_node_id
    source = find_source_node(graph, anchor_id)
    if source_node_id:
        for node in graph_nodes(graph):
            if str(node.get("id")) == str(source_node_id):
                source = node
                break
    source_id = (
        str(source.get("id"))
        if source
        else (source_node_id or anchor_id or "csv_reader-1")
    )
    source_type = node_type_of(source) if source else "csv_reader"
    origin = _source_position(source)
    if anchor_id:
        for node in graph_nodes(graph):
            if str(node.get("id")) == str(anchor_id):
                origin = _source_position(node)
                break
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

    schema_columns = [
        str(item.get("name"))
        for item in (inspect_result.get("fields") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    filter_spec = resolve_filter_spec(prompt, schema_columns)
    enriched_inspect = enrich_inspect_geometry_flags(inspect_result)

    structured_intent = bool(
        filter_spec
        or writer_type
        or (_wants_python(prompt) and filter_spec)
        or (_wants_reproject(prompt) and re.search(r"epsg|cc\s*\d|lambert|wgs", prompt or "", re.I))
    )

    if mapping_choice_id:
        choice = resolve_mapping_choice(mapping_choice_id, schema_columns)
        created_ids: Dict[str, str] = {}
        if not choice:
            events.append(
                _event(
                    "error",
                    content=f"Option de mappage inconnue : {mapping_choice_id}",
                )
            )
            return _composer_finish(events, created_ids, source_id)
        events.append(
            _event(
                "thought",
                content=(
                    f"Application de {choice.get('label') or mapping_choice_id} "
                    f"— {choice.get('description') or ''}"
                ),
            )
        )
        _emit_mapping_choice_pipeline(
            events,
            graph,
            source_id=source_id,
            origin=origin,
            choice=choice,
            created_ids=created_ids,
        )
        return _composer_finish(events, created_ids, source_id)

    if (
        needs_mapping_guidance(prompt)
        and not mapping_has_explicit_detail(prompt, schema_columns)
        and not structured_intent
    ):
        _append_mapping_guidance_events(
            events,
            prompt=prompt,
            schema_columns=schema_columns,
        )
        return _composer_finish(events, {}, source_id)

    if (
        needs_mapping_guidance(prompt)
        and mapping_has_explicit_detail(prompt, schema_columns)
        and not structured_intent
    ):
        default_id = (
            "dedupe_essential"
            if wants_data_cleaning_intent(prompt) and not wants_mapping_intent(prompt)
            else "snake_case"
        )
        choice = resolve_mapping_choice(default_id, schema_columns)
        created_ids = {}
        if choice:
            events.append(
                _event(
                    "thought",
                    content=(
                        f"Mappage ciblé détecté — application de "
                        f"{choice.get('label') or default_id}."
                    ),
                )
            )
            _emit_mapping_choice_pipeline(
                events,
                graph,
                source_id=source_id,
                origin=origin,
                choice=choice,
                created_ids=created_ids,
            )
            return _composer_finish(events, created_ids, source_id)

    use_filter_writer = bool(filter_spec) and writer_type in {
        "gpkg_writer",
        "geojson_writer",
        "shapefile_writer",
        "csv_writer",
        "postgis_writer",
    }

    created_ids: Dict[str, str] = {}
    branches = _build_composer_branches(prompt, schema_columns, writer_type)
    step_kinds: List[str] = []
    writer_labels = {
        "gpkg_writer": "GeoPackage (.gpkg)",
        "geojson_writer": "GeoJSON (.geojson)",
        "shapefile_writer": "Shapefile (.shp)",
        "csv_writer": "CSV (.csv)",
        "postgis_writer": "PostGIS",
    }

    if len(branches) >= 2:
        step_kinds = ["attribute_filter", "export"]
        events.append(
            _event(
                "thought",
                content=(
                    f"{len(branches)} branche(s) parallèle(s) depuis la source "
                    f"(décalage Y = {int(COMPOSER_BRANCH_OFFSET_Y)} px) — "
                    "un nœud filtre et un writer par branche lorsque demandé."
                ),
            )
        )
        for branch_id, branch in enumerate(branches):
            if branch.filter_spec or branch.writer_type:
                label = writer_labels.get(branch.writer_type or "", branch.writer_type or "")
                fs = branch.filter_spec
                if fs and branch.writer_type:
                    detail = (
                        f"Branche {branch_id + 1} : filtre {fs['field']} "
                        f"{fs.get('operator')} {fs['value']} → {label}"
                    )
                elif fs:
                    detail = (
                        f"Branche {branch_id + 1} : filtre {fs['field']} "
                        f"{fs.get('operator')} {fs['value']}"
                    )
                else:
                    detail = f"Branche {branch_id + 1} : export {label}"
                events.append(_event("thought", content=detail))
            _emit_branch_pipeline(
                events,
                graph,
                source_id=source_id,
                origin=origin,
                branch_index=branch_id,
                filter_spec=branch.filter_spec,
                writer_type=branch.writer_type,
                inspect=enriched_inspect,
                created_ids=created_ids,
            )

    elif use_filter_writer and filter_spec:
        step_kinds = ["attribute_filter", "export"]
        out_type = writer_type or "gpkg_writer"
        op_label = {">": ">", "gt": ">", "gte": ">=", "lt": "<", "eq": "="}.get(
            filter_spec["operator"], filter_spec["operator"]
        )
        events.append(
            _event(
                "thought",
                content=(
                    f"Filtrage de la colonne '{filter_spec['field']}' "
                    f"{op_label} {filter_spec['value']}, "
                    f"puis export {writer_labels.get(out_type, out_type)}."
                ),
            )
        )
        _emit_branch_pipeline(
            events,
            graph,
            source_id=source_id,
            origin=origin,
            branch_index=0,
            filter_spec=filter_spec,
            writer_type=out_type,
            inspect=enriched_inspect,
            created_ids=created_ids,
        )
        if _wants_python(prompt):
            code = _python_filter_code(
                filter_spec["field"],
                filter_spec["operator"],
                filter_spec["value"],
            )
            py_args = {
                "node_type": "python_caller",
                "position": {
                    "x": origin["x"] + COMPOSER_STEP_OFFSET_X,
                    "y": origin["y"] + COMPOSER_BRANCH_OFFSET_Y,
                },
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

    elif filter_spec and not use_filter_writer and not _wants_python(prompt):
        step_kinds = ["attribute_filter"]
        op_label = {
            ">": ">",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "eq": "=",
            "contains": "contient",
        }.get(filter_spec["operator"], filter_spec["operator"])
        events.append(
            _event(
                "thought",
                content=(
                    f"Filtre attributaire : colonne « {filter_spec['field']} » "
                    f"{op_label} {filter_spec['value']} "
                    f"(correspondance schéma amont parmi {len(schema_columns)} attribut(s))."
                ),
            )
        )
        _emit_branch_pipeline(
            events,
            graph,
            source_id=source_id,
            origin=origin,
            branch_index=0,
            filter_spec=filter_spec,
            writer_type=None,
            inspect=enriched_inspect,
            created_ids=created_ids,
        )

    elif writer_type and not filter_spec and not _wants_python(prompt):
        step_kinds = ["export"]
        events.append(
            _event(
                "thought",
                content=f"Export direct vers {writer_labels.get(writer_type, writer_type)}.",
            )
        )
        _emit_branch_pipeline(
            events,
            graph,
            source_id=source_id,
            origin=origin,
            branch_index=0,
            filter_spec=None,
            writer_type=writer_type,
            inspect=enriched_inspect,
            created_ids=created_ids,
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
        source_crs = normalize_crs(inspect_result.get("crs"))
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
                "source_crs": source_crs,
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
            if wants_filter_intent(prompt) and not filter_spec:
                col_preview = ", ".join(schema_columns[:8]) if schema_columns else "—"
                events.append(
                    _event(
                        "thought",
                        content=(
                            "Intention de filtrage détectée, mais aucune colonne du schéma "
                            f"ne correspond clairement à votre consigne (colonnes vues : {col_preview}). "
                            "Précisez le nom d’attribut ou exécutez Test step sur le reader amont."
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

    if created_ids:
        _append_proactive_suggestions(
            events,
            prompt,
            enriched_inspect,
            step_kinds or ["export"],
        )

    return _composer_finish(events, created_ids, source_id)


def extract_tool_sequence(events: List[Dict[str, Any]]) -> List[str]:
    return [
        str(item.get("summary"))
        for item in events
        if item.get("type") == "tool_call"
        and item.get("name") in {"create_canvas_node", "connect_nodes"}
    ]
