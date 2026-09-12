"""Détection de géométrie et auto-healing pour exports spatiaux (SHP, GeoJSON, GPKG)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.readers.tabular import find_xy_columns

_SPATIAL_WRITERS = frozenset(
    {"shapefile_writer", "vector_writer", "geojson_writer", "gpkg_writer", "file_writer"}
)

_GEOMETRY_ERROR_RE = re.compile(
    r"geometry|géométrie|geodataframe|crs|coordonn",
    re.IGNORECASE,
)


def is_spatial_writer(node_type: str) -> bool:
    key = (node_type or "").lower()
    if key in _SPATIAL_WRITERS:
        return True
    return key.endswith("_writer") and key not in {"csv_writer", "postgis_writer"}


def field_names(inspect: Dict[str, Any]) -> List[str]:
    fields = inspect.get("fields") if isinstance(inspect.get("fields"), list) else []
    return [
        str(item.get("name"))
        for item in fields
        if isinstance(item, dict) and item.get("name")
    ]


def coordinate_pair(inspect: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    pair = find_xy_columns(field_names(inspect))
    if pair:
        return pair
    meta = inspect.get("metadata") if isinstance(inspect.get("metadata"), dict) else {}
    cols = meta.get("coordinate_columns")
    if isinstance(cols, list) and len(cols) >= 2:
        return str(cols[0]), str(cols[1])
    params = inspect.get("params") if isinstance(inspect.get("params"), dict) else {}
    cols = params.get("coordinate_columns")
    if isinstance(cols, list) and len(cols) >= 2:
        return str(cols[0]), str(cols[1])
    return None


def inspect_has_geometry(inspect: Dict[str, Any]) -> bool:
    if inspect.get("has_geometry") is True:
        return True
    geom_types = inspect.get("geometry_types")
    if isinstance(geom_types, list) and geom_types:
        return True
    geom = inspect.get("geometry")
    if geom and str(geom).strip().lower() not in {"none", "—", "-", ""}:
        return True
    return False


def enrich_inspect_geometry_flags(inspect: Dict[str, Any]) -> Dict[str, Any]:
    """Ajoute has_geometry et coordinate_columns à un résultat inspect_input_schema."""
    out = dict(inspect)
    pair = coordinate_pair(out)
    if pair:
        out["coordinate_columns"] = [pair[0], pair[1]]
    out["has_geometry"] = inspect_has_geometry(out)
    return out


def geometry_builder_python_code(x_col: str, y_col: str) -> str:
    return (
        "# Création de points à partir des colonnes X/Y (auto-healing)\n"
        "import pandas as pd\n"
        "from shapely.geometry import Point\n"
        f"x_col, y_col = '{x_col}', '{y_col}'\n"
        "work = gdf.copy()\n"
        "if x_col not in work.columns or y_col not in work.columns:\n"
        "    raise ValueError(f'Colonnes {x_col}/{y_col} introuvables pour créer la géométrie.')\n"
        "work[x_col] = pd.to_numeric(work[x_col], errors='coerce')\n"
        "work[y_col] = pd.to_numeric(work[y_col], errors='coerce')\n"
        "work = work.dropna(subset=[x_col, y_col])\n"
        "geometry = [Point(xy) for xy in zip(work[x_col], work[y_col], strict=True)]\n"
        "output_gdf = work.drop(columns=[x_col, y_col], errors='ignore')\n"
        "output_gdf = output_gdf.set_geometry(geometry, crs=gdf.crs or 'EPSG:4326')\n"
        "return output_gdf\n"
    )


def resolve_spatial_export_writer(
    writer_type: str,
    inspect: Dict[str, Any],
) -> Tuple[str, Dict[str, Any], List[str]]:
    """
    Retourne (writer_type, config_extra, messages utilisateur).
    Insère la logique de repli CSV si aucune géométrie ni colonnes XY.
    """
    messages: List[str] = []
    if not is_spatial_writer(writer_type):
        return writer_type, {}, messages
    if inspect_has_geometry(inspect):
        return writer_type, {}, messages
    pair = coordinate_pair(inspect)
    if pair:
        return writer_type, {"_geometry_heal": {"x": pair[0], "y": pair[1]}}, messages
    messages.append(
        "Données sans géométrie ni colonnes X/Y détectées — export basculé en CSV "
        "(au lieu de Shapefile/GeoJSON)."
    )
    return "csv_writer", {}, messages


def geometry_heal_step_config(inspect: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Config d'un nœud python_caller pour reconstruire la géométrie, ou None."""
    if inspect_has_geometry(inspect):
        return None
    pair = coordinate_pair(inspect)
    if not pair:
        return None
    x_col, y_col = pair
    return {
        "language": "python",
        "code": geometry_builder_python_code(x_col, y_col),
    }


def build_proactive_suggestions(
    global_objective: str,
    inspect: Dict[str, Any],
    step_kinds: List[str],
) -> List[str]:
    objective = (global_objective or "").lower()
    suggestions: List[str] = []
    crs = str(inspect.get("crs") or "").upper()
    if "2154" not in objective and "reproj" not in objective and "rgf" not in objective:
        if crs and "2154" not in crs:
            suggestions.append(
                "Voulez-vous reprojeter les données en RGF93 / EPSG:2154 ?"
            )
    if "attribute_filter" in step_kinds or "filtre" in objective:
        suggestions.append(
            "Souhaitez-vous exporter un rapport statistique des entités filtrées (CSV) ?"
        )
    if inspect_has_geometry(inspect) and "geojson" not in objective:
        suggestions.append(
            "Voulez-vous dupliquer le résultat en GeoJSON pour la visualisation web ?"
        )
    return suggestions[:3]


def is_geometry_related_error(error_message: str) -> bool:
    return bool(_GEOMETRY_ERROR_RE.search(error_message or ""))


def explain_geometry_error(error_message: str) -> str:
    text = (error_message or "").strip()
    lower = text.lower()
    if "without a geometry column" in lower or "geometry column" in lower:
        return (
            "L'export Shapefile a échoué : les données en entrée n'ont pas de géométrie "
            "(souvent un CSV purement tabulaire). Il faut créer des points à partir des "
            "colonnes X/Y ou Latitude/Longitude, ou exporter en CSV."
        )
    if "crs" in lower:
        return (
            "Erreur de système de coordonnées (CRS) : la couche n'a pas de CRS valide ou "
            "la reprojection est impossible avec la géométrie actuelle."
        )
    return f"Échec lié à la géométrie ou au CRS : {text[:400]}"
