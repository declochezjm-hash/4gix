"""Assemblage Shapefile (.shp/.shx/.dbf) et messages guidés."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set

from app.core.paths import workspace_subdir
from app.core.shapefile_import import validate_zip_shapefile

SHAPEFILE_INCOMPLETE_CHAT_MESSAGE = (
    "Un Shapefile nécessite au minimum les fichiers .shp, .shx et .dbf. "
    "Veuillez téléverser une archive .zip contenant l'ensemble de ces fichiers."
)

SHAPEFILE_REQUIRED_EXTS = (".shx", ".dbf")


def is_shapefile_incomplete_error(message: str) -> bool:
    lower = (message or "").lower()
    return (
        "shapefile incomplet" in lower
        or "manque .shx" in lower
        or "manque .dbf" in lower
        or "sans shapefile complet" in lower
        or SHAPEFILE_INCOMPLETE_CHAT_MESSAGE.lower() in lower
    )


def shapefile_incomplete_chat_message(_error_message: str = "") -> str:
    return SHAPEFILE_INCOMPLETE_CHAT_MESSAGE


class ShapefileIncompleteError(ValueError):
    """Sidecars manquants pour un .shp isolé."""

    def __init__(self, detail: str, *, missing: Optional[List[str]] = None) -> None:
        self.missing = missing or []
        super().__init__(detail)


def _is_upload_uuid_prefix(prefix: str) -> bool:
    return len(prefix) == 10 and all(ch in "0123456789abcdef" for ch in prefix.lower())


def logical_stem(filename: str) -> str:
    stem = Path(filename).stem
    if "-" not in stem:
        return stem
    prefix, rest = stem.split("-", 1)
    if _is_upload_uuid_prefix(prefix) and rest:
        return rest
    return stem


def glob_sidecar(directory: Path, layer_stem: str, ext: str) -> Optional[Path]:
    for pattern in (f"{layer_stem}{ext}", f"*-{layer_stem}{ext}"):
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    return None


def search_dirs_for_shapefile(shp_path: Path) -> List[Path]:
    dirs: List[Path] = [shp_path.parent.resolve()]
    uploads = workspace_subdir("uploads", create=False)
    if uploads.is_dir():
        resolved = uploads.resolve()
        if resolved not in dirs:
            dirs.append(resolved)
    return dirs


def find_matching_zip_in_uploads(layer_stem: str) -> Optional[Path]:
    """Cherche une archive .zip complète dont une couche correspond au stem."""
    uploads = workspace_subdir("uploads", create=False)
    if not uploads.is_dir():
        return None
    layer_key = layer_stem.strip().lower()
    if not layer_key:
        return None

    candidates: List[Path] = []
    for zip_path in uploads.glob("*.zip"):
        zip_stem = logical_stem(zip_path.name).lower()
        if zip_stem == layer_key or layer_key in zip_stem or zip_stem in layer_key:
            candidates.append(zip_path)

    for zip_path in sorted(
        candidates,
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        raw = zip_path.read_bytes()
        ok, shape_sets, _components = validate_zip_shapefile(raw)
        if not ok:
            continue
        for item in shape_sets:
            name = str(item.get("layer_name") or "").lower()
            stem = Path(str(item.get("stem") or "")).name.lower()
            if name == layer_key or stem == layer_key:
                return zip_path
        if shape_sets:
            return zip_path
    return None


def collect_shapefile_parts(shp_path: Path) -> Dict[str, Path]:
    """Rassemble .shp/.shx/.dbf depuis le dossier local et uploads/."""
    shp_path = shp_path.resolve()
    if shp_path.suffix.lower() != ".shp":
        raise ValueError(f"Attendu un fichier .shp, reçu: {shp_path.name}")

    layer = logical_stem(shp_path.name)
    stem = shp_path.with_suffix("")
    parts: Dict[str, Path] = {".shp": shp_path}
    optional = (".prj", ".cpg", ".sbn", ".sbx", ".xml", ".qix", ".fix")

    for ext in SHAPEFILE_REQUIRED_EXTS + optional:
        local = stem.with_suffix(ext)
        if local.is_file():
            parts[ext] = local
            continue
        for directory in search_dirs_for_shapefile(shp_path):
            found = glob_sidecar(directory, layer, ext)
            if found and found.is_file():
                parts[ext] = found.resolve()
                break

    missing = [ext for ext in SHAPEFILE_REQUIRED_EXTS if ext not in parts]
    if missing:
        raise ShapefileIncompleteError(
            f"Shapefile incomplet ({shp_path.name}) : manque {', '.join(missing)}.",
            missing=missing,
        )
    return parts


def group_upload_sidecars_by_layer(uploads_dir: Path) -> Dict[str, Set[str]]:
    """Indexe les extensions présentes par nom de couche (hors préfixe upload)."""
    grouped: Dict[str, Set[str]] = {}
    if not uploads_dir.is_dir():
        return grouped
    for path in uploads_dir.iterdir():
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in {".shp", ".shx", ".dbf", *optional_extensions()}:
            continue
        layer = logical_stem(path.name)
        grouped.setdefault(layer, set()).add(ext)
    return grouped


def optional_extensions() -> Set[str]:
    return {".prj", ".cpg", ".sbn", ".sbx", ".xml", ".qix", ".fix"}
