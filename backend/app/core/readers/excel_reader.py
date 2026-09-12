"""Lecture Excel (.xlsx / .xls)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from app.core.paths import workspace_subdir
from app.core.readers.tabular import tabular_read_outputs
from app.core.shapefile_bundle import logical_stem

EXCEL_MISSING_OPENPYXL_MESSAGE = (
    "Le moteur de lecture Excel (openpyxl) est absent sur le serveur. "
    "Pour débloquer immédiatement le traitement, vous pouvez exporter votre fichier "
    "sous format .csv et le déposer sur le canvas."
)


class ExcelEngineError(RuntimeError):
    """openpyxl / xlrd indisponible ou lecture Excel impossible."""


def is_openpyxl_import_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if EXCEL_MISSING_OPENPYXL_MESSAGE.lower() in text:
        return True
    if "openpyxl" not in text:
        return False
    return any(
        token in text
        for token in ("import", "install", "missing", "optional dependency", "absent")
    )


def _excel_engine(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return "openpyxl"
    if suffix == ".xls":
        return "xlrd"
    return "openpyxl"


def _search_dirs_for_excel(path: Path) -> list[Path]:
    dirs = [path.parent.resolve()]
    uploads = workspace_subdir("uploads", create=False)
    if uploads.is_dir():
        resolved = uploads.resolve()
        if resolved not in dirs:
            dirs.append(resolved)
    return dirs


def find_csv_fallback_for_excel(excel_path: Path) -> Optional[Path]:
    """Cherche un .csv homonyme (même couche) à côté du fichier ou dans uploads/."""
    layer = logical_stem(excel_path.name)
    if not layer:
        return None
    for directory in _search_dirs_for_excel(excel_path):
        for pattern in (f"{layer}.csv", f"*-{layer}.csv"):
            matches = sorted(directory.glob(pattern))
            for candidate in matches:
                if candidate.is_file():
                    return candidate.resolve()
    return None


def _read_csv_fallback(
    excel_path: Path,
    csv_path: Path,
    *,
    sheet_name: Optional[str],
) -> Dict[str, Any]:
    df = pd.read_csv(csv_path, sep=None, engine="python", encoding="utf-8")
    if df.empty:
        df = pd.DataFrame()
    return tabular_read_outputs(
        df,
        source="excel",
        path=str(excel_path),
        extra_meta={
            "sheet_name": sheet_name or "csv_fallback",
            "sheets": [],
            "excel_fallback_csv": True,
            "csv_fallback_path": str(csv_path),
            "excel_fallback_notice": (
                f"Lecture Excel impossible — repli sur le CSV « {csv_path.name} »."
            ),
        },
    )


def open_excel_file(path: Path) -> pd.ExcelFile:
    engine = _excel_engine(path)
    try:
        return pd.ExcelFile(path, engine=engine)
    except ImportError as exc:
        if engine == "openpyxl" or is_openpyxl_import_error(exc):
            raise ExcelEngineError(EXCEL_MISSING_OPENPYXL_MESSAGE) from exc
        raise


def list_excel_sheets(path: Path) -> list[str]:
    book = open_excel_file(path)
    return list(book.sheet_names)


def read_excel_file(
    path: Path,
    *,
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Fichier Excel introuvable: {path}")

    engine = _excel_engine(path)

    try:
        book = open_excel_file(path)
        sheets = list(book.sheet_names)
    except ExcelEngineError:
        csv_path = find_csv_fallback_for_excel(path)
        if csv_path:
            return _read_csv_fallback(path, csv_path, sheet_name=sheet_name)
        raise
    except ImportError as exc:
        if is_openpyxl_import_error(exc):
            csv_path = find_csv_fallback_for_excel(path)
            if csv_path:
                return _read_csv_fallback(path, csv_path, sheet_name=sheet_name)
            raise ExcelEngineError(EXCEL_MISSING_OPENPYXL_MESSAGE) from exc
        raise

    if not sheets:
        raise ValueError("Fichier Excel sans feuille lisible.")

    active = sheet_name or sheets[0]
    if active not in sheets:
        raise ValueError(
            f"Feuille « {active} » absente. Feuilles disponibles : {', '.join(sheets)}.",
        )

    try:
        df = pd.read_excel(path, sheet_name=active, engine=engine)
    except ImportError as exc:
        if is_openpyxl_import_error(exc):
            csv_path = find_csv_fallback_for_excel(path)
            if csv_path:
                return _read_csv_fallback(path, csv_path, sheet_name=active)
            raise ExcelEngineError(EXCEL_MISSING_OPENPYXL_MESSAGE) from exc
        raise
    except ValueError as exc:
        if is_openpyxl_import_error(exc):
            csv_path = find_csv_fallback_for_excel(path)
            if csv_path:
                return _read_csv_fallback(path, csv_path, sheet_name=active)
            raise ExcelEngineError(EXCEL_MISSING_OPENPYXL_MESSAGE) from exc
        raise

    if df.empty:
        df = pd.DataFrame()

    return tabular_read_outputs(
        df,
        source="excel",
        path=str(path),
        extra_meta={"sheet_name": active, "sheets": sheets},
    )
