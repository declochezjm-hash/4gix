from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import geopandas as gpd

from app.core.paths import resolve_workspace_path, workspace_subdir
from app.core.readers.shapefile import shapefile_read_outputs
from app.nodes.base import Base4GIxNode

SHAPEFILE_SIDECAR = (".shx", ".dbf", ".prj", ".cpg")
SHAPEFILE_OPTIONAL = (".prj", ".cpg", ".sbn", ".sbx", ".xml", ".qix", ".fix")


def _is_upload_uuid_prefix(prefix: str) -> bool:
    return len(prefix) == 10 and all(ch in "0123456789abcdef" for ch in prefix.lower())


def _logical_stem(filename: str) -> str:
    """Nom de couche sans préfixe d'upload `xxxxxxxxxx-`."""
    stem = Path(filename).stem
    if "-" not in stem:
        return stem
    prefix, rest = stem.split("-", 1)
    if _is_upload_uuid_prefix(prefix) and rest:
        return rest
    return stem


def _glob_sidecar(directory: Path, logical_stem: str, ext: str) -> Optional[Path]:
    for pattern in (f"{logical_stem}{ext}", f"*-{logical_stem}{ext}"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def _search_dirs_for_shapefile(shp_path: Path) -> List[Path]:
    dirs: List[Path] = [shp_path.parent.resolve()]
    uploads = workspace_subdir("uploads", create=False)
    if uploads.is_dir():
        resolved = uploads.resolve()
        if resolved not in dirs:
            dirs.append(resolved)
    return dirs


def _collect_shapefile_parts(shp_path: Path) -> Dict[str, Path]:
    """Rassemble .shp/.shx/.dbf (et sidecars optionnels) pour une lecture Fiona."""
    shp_path = shp_path.resolve()
    if shp_path.suffix.lower() != ".shp":
        raise ValueError(f"Attendu un fichier .shp, reçu: {shp_path.name}")

    logical = _logical_stem(shp_path.name)
    stem = shp_path.with_suffix("")
    parts: Dict[str, Path] = {".shp": shp_path}

    for ext in SHAPEFILE_SIDECAR + tuple(
        item for item in SHAPEFILE_OPTIONAL if item not in SHAPEFILE_SIDECAR
    ):
        local = stem.with_suffix(ext)
        if local.is_file():
            parts[ext] = local
            continue
        for directory in _search_dirs_for_shapefile(shp_path):
            found = _glob_sidecar(directory, logical, ext)
            if found and found.is_file():
                parts[ext] = found.resolve()
                break

    missing = [ext for ext in (".shx", ".dbf") if ext not in parts]
    if missing:
        raise ValueError(
            f"Shapefile incomplet ({shp_path.name}) : manque {', '.join(missing)} "
            f"dans {shp_path.parent} ou dans uploads/. "
            "Glissez une archive .zip contenant .shp, .shx et .dbf (recommandé).",
        )
    return parts


def _resolve_shapefile_bundle(shp_path: Path) -> Path:
    """
    Retourne le chemin .shp à lire, en regroupant les sidecars (.dbf, .shx, …)
    dans un dossier unique si nécessaire (ex. .dbf dans uploads/).
    """
    parts = _collect_shapefile_parts(shp_path)
    logical = _logical_stem(shp_path.name)
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
        dest = bundle_dir / f"{logical}{ext}"
        if not dest.is_file() or src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
    staged = (bundle_dir / f"{logical}.shp").resolve()
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
            raise ValueError(
                f"Shapefile incomplet ({shp_path.name}) : manque {', '.join(missing)}. "
                "Glissez une archive .zip contenant .shp, .shx et .dbf (recommandé).",
            ) from exc
        raise
    if list(gdf.columns) == ["geometry"] or len(gdf.columns) <= 1:
        dbf = shp_path.with_suffix(".dbf")
        if not dbf.is_file():
            raise ValueError(
                f"Table d'attributs (.dbf) introuvable pour {shp_path.name}.",
            )
    return gdf


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

        if path.suffix.lower() == ".zip":
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
            geojson, map_geojson, meta = _geojson_payload(gdf)
            meta["zip_path"] = str(path)
            return {
                "data": geojson,
                "map_geojson": map_geojson,
                "metadata": meta,
            }

        if not path.is_file():
            raise FileNotFoundError(
                f"Shapefile introuvable: {path} (vérifiez le chemin /workspace ou réimportez le fichier).",
            )

        gdf = _read_shapefile_path(path, encoding)
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
