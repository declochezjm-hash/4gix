from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd

from app.core.paths import resolve_workspace_path, workspace_subdir
from app.core.readers.shapefile import shapefile_read_outputs
from app.core.shapefile_bundle import (
    SHAPEFILE_INCOMPLETE_CHAT_MESSAGE,
    ShapefileIncompleteError,
    collect_shapefile_parts,
    find_matching_zip_in_uploads,
    is_shapefile_incomplete_error,
    logical_stem,
    shapefile_incomplete_chat_message,
)
from app.nodes.base import Base4GIxNode

__all__ = [
    "ShapefileReader",
    "SHAPEFILE_INCOMPLETE_CHAT_MESSAGE",
    "ShapefileIncompleteError",
    "is_shapefile_incomplete_error",
    "shapefile_incomplete_chat_message",
]


def _resolve_shapefile_bundle(shp_path: Path) -> Path:
    """
    Retourne le chemin .shp à lire, en regroupant les sidecars (.dbf, .shx, …)
    dans un dossier unique si nécessaire (ex. .dbf dans uploads/).
    """
    parts = collect_shapefile_parts(shp_path)
    layer = logical_stem(shp_path.name)
    target_stem = shp_path.with_suffix("").resolve()
    needs_stage = False
    for ext, src in parts.items():
        if ext == ".shp":
            continue
        expected = target_stem.with_suffix(ext)
        if src.resolve() != expected.resolve():
            needs_stage = True
            break

    if not needs_stage:
        return shp_path.resolve()

    bundle_dir = workspace_subdir("imports", f"bundle-{uuid.uuid4().hex[:10]}", create=True)
    for ext, src in parts.items():
        dest = bundle_dir / f"{layer}{ext}"
        if not dest.is_file() or src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
    staged = (bundle_dir / f"{layer}.shp").resolve()
    if not staged.is_file():
        raise FileNotFoundError(f"Assemblage Shapefile incomplet pour {shp_path.name}.")
    return staged


def _encoding_from_cpg(shp_path: Path) -> Optional[str]:
    cpg = shp_path.with_suffix(".cpg")
    if not cpg.is_file():
        return None
    text = cpg.read_text(encoding="utf-8", errors="ignore").strip()
    return text or None


def _pick_shapefile_set(
    sets: List[Dict[str, Any]],
    layer_name: Optional[str],
) -> Dict[str, Any]:
    if not sets:
        raise ValueError("Archive .zip sans Shapefile complet (.shp + .shx + .dbf).")
    if layer_name:
        key = layer_name.strip().lower()
        for item in sets:
            if item.get("layer_name", "").lower() == key:
                return item
            stem = Path(str(item.get("stem", ""))).name.lower()
            if stem == key:
                return item
    return sets[0]


def _read_shapefile_path(path: Path, encoding: Optional[str]) -> gpd.GeoDataFrame:
    """Lit un .shp après vérification/assemblage .shx + .dbf (y compris depuis uploads/)."""
    shp_path = _resolve_shapefile_bundle(path)
    os.environ.setdefault("SHAPE_RESTORE_SHX", "YES")
    kwargs: Dict[str, Any] = {}
    resolved_encoding = encoding or _encoding_from_cpg(shp_path)
    if resolved_encoding:
        kwargs["encoding"] = resolved_encoding
    try:
        gdf = gpd.read_file(shp_path, **kwargs)
    except Exception as exc:
        missing = [
            ext
            for ext in (".shx", ".dbf")
            if not shp_path.with_suffix(ext).is_file()
        ]
        if missing:
            raise ShapefileIncompleteError(
                f"Shapefile incomplet ({shp_path.name}) : manque {', '.join(missing)}.",
                missing=missing,
            ) from exc
        raise
    if list(gdf.columns) == ["geometry"] or len(gdf.columns) <= 1:
        dbf = shp_path.with_suffix(".dbf")
        if not dbf.is_file():
            raise ShapefileIncompleteError(
                f"Table d'attributs (.dbf) introuvable pour {shp_path.name}.",
                missing=[".dbf"],
            )
    return gdf


def _read_from_zip_path(
    path: Path,
    layer_name: Optional[str],
) -> tuple[gpd.GeoDataFrame, Dict[str, Any]]:
    from app.core.shapefile_import import (
        _extract_shapefile_sidecars,
        _geojson_payload,
        _read_geodataframe,
        discover_shapefile_sets,
        list_zip_entries,
    )

    if not path.is_file():
        raise FileNotFoundError(f"Archive Shapefile introuvable: {path}")
    entries = list_zip_entries(path.read_bytes())
    sets = discover_shapefile_sets(entries)
    chosen = _pick_shapefile_set(sets, layer_name)
    inner_shp = chosen["shp_path_in_zip"]
    shp_file = _extract_shapefile_sidecars(path, inner_shp)
    gdf = _read_geodataframe(shp_file)
    _geojson, _map, meta = _geojson_payload(gdf)
    meta["zip_path"] = str(path)
    return gdf, meta


def _resolve_shp_or_zip(path: Path, layer_name: Optional[str]) -> tuple[Path, bool]:
    """
    Retourne (chemin_effectif, from_zip).
    Tente une archive .zip homonyme dans uploads/ si le .shp est incomplet.
    """
    if path.suffix.lower() == ".zip":
        return path, True
    if path.suffix.lower() != ".shp":
        return path, False

    try:
        collect_shapefile_parts(path)
        return path, False
    except ShapefileIncompleteError:
        layer = logical_stem(path.name)
        zip_path = find_matching_zip_in_uploads(layer)
        if zip_path:
            return zip_path, True
        raise


class ShapefileReader(Base4GIxNode):
    node_type = "shapefile_reader"
    category = "Reader"
    is_spatial = True
    label = "Shapefile Reader"
    description = "Lit un Shapefile (.shp) ou une archive .zip contenant un Shapefile."

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Shapefile Reader",
            "description": "Source ESRI Shapefile (fichier .shp ou archive .zip).",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Chemin .shp",
                    "description": "Chemin extrait dans /workspace ou URI zip://…",
                    "default": "/workspace/imports/sample/layer.shp",
                },
                "zip_path": {
                    "type": "string",
                    "title": "Archive .zip source (optionnel)",
                    "description": "Chemin de l'archive d'origine si import drag-and-drop.",
                },
                "layer_name": {
                    "type": "string",
                    "title": "Nom de couche",
                },
                "encoding": {
                    "type": "string",
                    "title": "Encodage attributs (.cpg)",
                    "default": "utf-8",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = (
            params.get("path")
            or params.get("file_path")
            or params.get("zip_path")
            or ""
        ).strip()
        if not raw_path:
            raise ValueError("Paramètre `path` manquant pour Shapefile Reader.")

        path = resolve_workspace_path(raw_path)
        layer_name = (params.get("layer_name") or "").strip() or None
        encoding = (params.get("encoding") or "").strip() or None

        zip_hint = (params.get("zip_path") or "").strip()
        if zip_hint and path.suffix.lower() != ".zip":
            zip_resolved = resolve_workspace_path(zip_hint)
            if zip_resolved.is_file():
                path = zip_resolved

        if not path.is_file():
            raise FileNotFoundError(
                f"Shapefile introuvable: {path} (vérifiez le chemin /workspace ou réimportez le fichier).",
            )

        try:
            effective, from_zip = _resolve_shp_or_zip(path, layer_name)
        except ShapefileIncompleteError as exc:
            raise ShapefileIncompleteError(
                SHAPEFILE_INCOMPLETE_CHAT_MESSAGE,
                missing=exc.missing,
            ) from exc

        if from_zip or effective.suffix.lower() == ".zip":
            gdf, zip_meta = _read_from_zip_path(effective, layer_name)
            geojson, map_geojson, meta = shapefile_read_outputs(gdf)
            meta.update(zip_meta)
            meta["columns"] = [col for col in gdf.columns if col != "geometry"]
            return {
                "data": geojson,
                "map_geojson": map_geojson,
                "metadata": meta,
            }

        gdf = _read_shapefile_path(effective, encoding)
        geojson, map_geojson, meta = shapefile_read_outputs(gdf)
        meta["columns"] = [col for col in gdf.columns if col != "geometry"]
        meta.update(
            {
                "source": "shapefile",
                "path": str(path),
                "zip_path": params.get("zip_path"),
                "layer_name": params.get("layer_name"),
            },
        )
        return {
            "data": geojson,
            "map_geojson": map_geojson,
            "metadata": meta,
        }
