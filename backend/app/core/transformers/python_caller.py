"""Moteur d'exécution Python utilisateur (GeoPandas) — sans dépendance au registre de nœuds."""

from __future__ import annotations

import json
import re
import traceback
from typing import Any, Dict, List, Optional

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from sqlalchemy import create_engine, text

DEFAULT_CODE = """# Transformer les données entrantes avec GeoPandas
# 'gdf' contient le GeoDataFrame courant (géométries + attributs)

gdf['surface_m2'] = gdf.geometry.area
output_gdf = gdf[gdf['surface_m2'] > 100]

return output_gdf
"""

DEFAULT_SQL = """-- Tables disponibles : items, gdf (attributs + __row_id__)
-- Conservez __row_id__ pour garder les géométries sur la sortie.

SELECT *
FROM items
WHERE 1 = 1
"""

_SAFE_BUILTINS: Dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}


def crs_hint(features: List[Dict[str, Any]]) -> str:
    for feature in features:
        props = feature.get("properties") or {}
        crs = props.get("fme_crs")
        if crs:
            return str(crs)
    return "EPSG:4326"


def features_to_gdf(features: List[Dict[str, Any]]) -> gpd.GeoDataFrame:
    if not features:
        return gpd.GeoDataFrame(geometry=[], crs=crs_hint(features))
    rows: List[Dict[str, Any]] = []
    geoms = []
    for feature in features:
        props = dict(feature.get("properties") or {})
        geom = feature.get("geometry")
        geoms.append(shape(geom) if geom else None)
        rows.append(props)
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=crs_hint(features))


def gdf_to_features(gdf: gpd.GeoDataFrame) -> List[Dict[str, Any]]:
    if gdf is None or gdf.empty:
        return []
    parsed = json.loads(gdf.to_json())
    return list(parsed.get("features") or [])


def _compile_user_fn(code: str) -> Any:
    body_lines = []
    for line in code.splitlines():
        body_lines.append(f"    {line}" if line.strip() else "")
    source = "def __user_fn(gdf, items, feature):\n" + "\n".join(body_lines) + "\n"
    return compile(source, "<python_caller>", "exec")


def _safe_globals() -> Dict[str, Any]:
    return {
        "__builtins__": _SAFE_BUILTINS,
        "gpd": gpd,
        "pd": pd,
    }


def _normalize_result(result: Any, fallback: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if result is None:
        return fallback
    if isinstance(result, gpd.GeoDataFrame):
        return result
    if isinstance(result, list):
        if not result:
            return gpd.GeoDataFrame(geometry=[], crs=fallback.crs)
        if isinstance(result[0], dict) and result[0].get("type") == "Feature":
            return features_to_gdf(result)
    raise TypeError(
        "Le script doit retourner un GeoDataFrame (ex. `return output_gdf`).",
    )


def run_user_code(
    code: str,
    *,
    gdf: gpd.GeoDataFrame,
    items: List[Dict[str, Any]],
    feature: Optional[Dict[str, Any]],
) -> gpd.GeoDataFrame:
    compiled = _compile_user_fn(code)
    namespace = _safe_globals()
    local: Dict[str, Any] = {}
    exec(compiled, namespace, local)  # noqa: S102
    fn = local.get("__user_fn") or namespace.get("__user_fn")
    if not callable(fn):
        raise RuntimeError("Impossible de compiler le script utilisateur.")
    result = fn(gdf, items, feature)
    return _normalize_result(result, gdf)


def attach_map_inspection(payload: Dict[str, Any], gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
    try:
        from app.core.readers.shapefile import shapefile_read_outputs

        _native, map_geojson, meta = shapefile_read_outputs(gdf)
        payload["map_geojson"] = map_geojson
        metadata = dict(payload.get("metadata") or {})
        if meta.get("bbox"):
            metadata["bbox"] = meta["bbox"]
        payload["metadata"] = metadata
    except Exception:  # noqa: BLE001
        pass
    return payload


def _assert_readonly_sql(sql: str) -> str:
    cleaned = sql.strip().rstrip(";")
    if not cleaned:
        raise ValueError("Requête SQL vide.")
    if ";" in cleaned:
        raise ValueError("Une seule instruction SQL SELECT est autorisée.")
    lowered = re.sub(r"\s+", " ", cleaned.lower())
    if not lowered.startswith("select"):
        raise ValueError("Seules les requêtes SELECT sont autorisées.")
    forbidden = ("insert ", "update ", "delete ", "drop ", "alter ", "create ", "attach ")
    for token in forbidden:
        if token in lowered:
            raise ValueError(f"Instruction SQL interdite : {token.strip()}.")
    return cleaned


def _tabular_for_sql(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    frame = gdf.drop(columns=["geometry"], errors="ignore").copy()
    frame.insert(0, "__row_id__", range(len(frame)))
    return frame


def _gdf_from_sql_result(result_df: pd.DataFrame, source: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    crs = source.crs
    if result_df.empty:
        return gpd.GeoDataFrame(geometry=[], crs=crs)
    if "__row_id__" in result_df.columns:
        ids = pd.to_numeric(result_df["__row_id__"], errors="coerce").astype("Int64")
        geoms = []
        attrs = result_df.drop(columns=["__row_id__"], errors="ignore")
        for row_id in ids:
            if pd.isna(row_id) or int(row_id) < 0 or int(row_id) >= len(source):
                geoms.append(None)
            else:
                geoms.append(source.geometry.iloc[int(row_id)])
        return gpd.GeoDataFrame(attrs, geometry=geoms, crs=crs)
    if len(result_df) == len(source):
        return gpd.GeoDataFrame(result_df, geometry=source.geometry.values, crs=crs)
    return gpd.GeoDataFrame(result_df, geometry=[None] * len(result_df), crs=crs)


def run_sql_on_gdf(code: str, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    sql = _assert_readonly_sql(code)
    tab = _tabular_for_sql(gdf)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        tab.to_sql("items", conn, index=False, if_exists="replace")
        conn.execute(text("CREATE VIEW gdf AS SELECT * FROM items"))
        result_df = pd.read_sql(text(sql), conn)
    return _gdf_from_sql_result(result_df, gdf)


def execute_sql_transform(
    *,
    node_type: str,
    features: List[Dict[str, Any]],
    code: str,
    mode: str,
) -> Dict[str, Any]:
    from app.nodes.fme_features import ports_payload

    try:
        if mode == "per_item":
            out_features: List[Dict[str, Any]] = []
            for feature in features:
                item_gdf = features_to_gdf([feature])
                result_gdf = run_sql_on_gdf(code, item_gdf)
                out_features.extend(gdf_to_features(result_gdf))
            result_gdf = features_to_gdf(out_features) if out_features else features_to_gdf([])
        else:
            gdf = features_to_gdf(features)
            result_gdf = run_sql_on_gdf(code, gdf)
            out_features = gdf_to_features(result_gdf)

        payload = ports_payload(
            {"output": out_features, "rejected": []},
            feature_type=node_type,
            crs=str(result_gdf.crs) if result_gdf.crs else crs_hint(features),
            extra_meta={"mode": mode, "language": "sql"},
        )
        return attach_map_inspection(payload, result_gdf)
    except Exception as exc:  # noqa: BLE001
        return error_payload(node_type, exc)


def execute_code_transform(
    *,
    node_type: str,
    features: List[Dict[str, Any]],
    code: str,
    mode: str,
    language: str,
) -> Dict[str, Any]:
    lang = (language or "python").lower()
    if lang == "sql":
        return execute_sql_transform(
            node_type=node_type,
            features=features,
            code=code,
            mode=mode,
        )
    return execute_python_transform(
        node_type=node_type,
        features=features,
        code=code,
        mode=mode,
    )


def error_payload(node_type: str, exc: BaseException) -> Dict[str, Any]:
    from app.nodes.fme_features import feature_from_shapely, ports_payload

    rejected = [
        feature_from_shapely(
            None,
            {
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
            feature_type=node_type,
            rejection_code="PYTHON_ERROR",
        ),
    ]
    return ports_payload(
        {"output": [], "rejected": rejected},
        feature_type=node_type,
        extra_meta={"python_error": str(exc)},
        primary="output",
    )


def execute_python_transform(
    *,
    node_type: str,
    features: List[Dict[str, Any]],
    code: str,
    mode: str,
) -> Dict[str, Any]:
    from app.nodes.fme_features import ports_payload

    items = [dict(feature.get("properties") or {}) for feature in features]
    try:
        if mode == "per_item":
            out_features: List[Dict[str, Any]] = []
            for index, feature in enumerate(features):
                item_gdf = features_to_gdf([feature])
                item_props = [items[index]] if index < len(items) else []
                result_gdf = run_user_code(
                    code,
                    gdf=item_gdf,
                    items=item_props,
                    feature=feature,
                )
                out_features.extend(gdf_to_features(result_gdf))
            result_gdf = features_to_gdf(out_features) if out_features else features_to_gdf([])
        else:
            gdf = features_to_gdf(features)
            result_gdf = run_user_code(code, gdf=gdf, items=items, feature=None)
            out_features = gdf_to_features(result_gdf)

        payload = ports_payload(
            {"output": out_features, "rejected": []},
            feature_type=node_type,
            crs=str(result_gdf.crs) if result_gdf.crs else crs_hint(features),
            extra_meta={"mode": mode},
        )
        return attach_map_inspection(payload, result_gdf)
    except Exception as exc:  # noqa: BLE001
        return error_payload(node_type, exc)
