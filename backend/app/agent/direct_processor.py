"""Exécution GeoPandas pilotée par LLM (sans sous-graphe canvas)."""

from __future__ import annotations

import re
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import httpx
from shapely.geometry import shape

from app.core.config import settings
from app.core.transformers.python_caller import (
    _SAFE_BUILTINS,
    attach_map_inspection,
    features_to_gdf,
    gdf_to_features,
)

_SYSTEM_INSTRUCTION = (
    "Tu es un moteur d'exécution spatial. Génère EXCLUSIVEMENT une fonction Python "
    "nommée `transform(gdf)` utilisant GeoPandas/Shapely pour répondre à la demande. "
    "Aucun texte explicatif, uniquement le code Python pur. "
    "La fonction doit retourner un GeoDataFrame."
)

_FENCE_RE = re.compile(r"```(?:python)?\s*([\s\S]*?)```", re.IGNORECASE)


def _safe_globals() -> Dict[str, Any]:
    import pandas as pd

    return {
        "__builtins__": _SAFE_BUILTINS,
        "gpd": gpd,
        "pd": pd,
        "shape": shape,
    }


def _sample_rows_text(gdf: gpd.GeoDataFrame, limit: int) -> str:
    if gdf is None or gdf.empty:
        return "(aucune ligne)"
    frame = gdf.drop(columns=["geometry"], errors="ignore").head(max(1, limit))
    lines: List[str] = []
    for idx, row in frame.iterrows():
        lines.append(f"  [{idx}] {row.to_dict()}")
    return "\n".join(lines)


def build_system_prompt(gdf: gpd.GeoDataFrame, sample_limit: int = 3) -> str:
    dtypes = gdf.dtypes.to_string() if gdf is not None and not gdf.empty else "(vide)"
    crs = str(gdf.crs) if gdf is not None and gdf.crs else "non défini"
    sample_n = min(3, max(1, sample_limit))
    sample = _sample_rows_text(gdf, sample_n)
    return (
        f"{_SYSTEM_INSTRUCTION}\n\n"
        f"Schéma d'entrée:\n"
        f"- CRS: {crs}\n"
        f"- dtypes:\n{dtypes}\n"
        f"- Exemple ({sample_n} lignes, attributs sans géométrie):\n{sample}\n"
    )


def extract_python_code(raw: str) -> str:
    text = (raw or "").strip()
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    if "def transform" in text:
        return text
    return text


def _normalize_transform_source(code: str) -> str:
    stripped = code.strip()
    if not stripped:
        raise ValueError("Code généré vide.")
    if "def transform" not in stripped:
        body_lines = []
        for line in stripped.splitlines():
            body_lines.append(f"    {line}" if line.strip() else "")
        stripped = "def transform(gdf):\n" + "\n".join(body_lines) + "\n"
    return stripped + ("\n" if not stripped.endswith("\n") else "")


def run_transform(code: str, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    source = _normalize_transform_source(code)
    namespace = _safe_globals()
    local: Dict[str, Any] = {}
    compiled = compile(source, "<direct_processor>", "exec")
    exec(compiled, namespace, local)  # noqa: S102
    fn = local.get("transform") or namespace.get("transform")
    if not callable(fn):
        raise RuntimeError("Le code doit définir une fonction transform(gdf).")
    result = fn(gdf.copy())
    if result is None:
        raise TypeError("transform(gdf) a retourné None ; attendu un GeoDataFrame.")
    if not isinstance(result, gpd.GeoDataFrame):
        raise TypeError("transform(gdf) doit retourner un GeoDataFrame.")
    return result


def call_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: Optional[str] = None,
) -> str:
    key = (api_key or "").strip() or (settings.openai_api_key or "").strip()
    if not key:
        raise ValueError(
            "Clé API manquante : fournissez api_key ou définissez FOURGIX_OPENAI_API_KEY.",
        )
    model_name = model or settings.openai_model
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }
    url = settings.openai_chat_completions_url
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    if response.status_code >= 400:
        detail = response.text[:500]
        raise RuntimeError(f"Appel LLM échoué ({response.status_code}): {detail}")
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Réponse LLM sans contenu.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Réponse LLM vide.")
    return content


def process_direct(
    gdf: gpd.GeoDataFrame,
    prompt: str,
    api_key: str,
    *,
    sample_limit: int = 3,
    llm_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Génère et exécute transform(gdf) via LLM.

    llm_code: injection de test (bypass LLM).
    """
    log_lines: List[str] = []
    started = time.perf_counter()
    system_prompt = build_system_prompt(gdf, sample_limit=sample_limit)
    log_lines.append("System prompt construit (schéma + échantillon).")

    try:
        raw_code = llm_code if llm_code is not None else call_llm(
            system_prompt=system_prompt,
            user_prompt=prompt,
            api_key=api_key,
        )
        code = extract_python_code(raw_code)
        log_lines.append("Code transform(gdf) reçu du LLM.")
        before = len(gdf) if gdf is not None else 0
        result_gdf = run_transform(code, gdf)
        after = len(result_gdf)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        log_lines.append(
            f"Exécution OK en {elapsed_ms:.1f} ms — entités {before} -> {after}.",
        )
        return {
            "ok": True,
            "gdf": result_gdf,
            "code": code,
            "log": "\n".join(log_lines),
            "feature_count_before": before,
            "feature_count_after": after,
            "duration_ms": elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        log_lines.append(f"Erreur: {exc}")
        log_lines.append(traceback.format_exc())
        return {
            "ok": False,
            "gdf": gdf,
            "code": llm_code or "",
            "log": "\n".join(log_lines),
            "error": str(exc),
            "duration_ms": elapsed_ms,
        }


def payload_from_gdf(
    gdf: gpd.GeoDataFrame,
    *,
    node_type: str,
    source_features: List[Dict[str, Any]],
) -> Dict[str, Any]:
    from app.nodes.workflow_features import ports_payload

    out_features = gdf_to_features(gdf)
    crs = str(gdf.crs) if gdf is not None and gdf.crs else None
    payload = ports_payload(
        {"output": out_features, "rejected": []},
        feature_type=node_type,
        crs=crs,
        extra_meta={"direct_processor": True},
    )
    if not crs and source_features:
        from app.core.transformers.python_caller import crs_hint

        payload.setdefault("metadata", {})
        payload["metadata"]["crs"] = crs_hint(source_features)
    return attach_map_inspection(payload, gdf)
