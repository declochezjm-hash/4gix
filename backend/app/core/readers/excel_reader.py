"""Lecture Excel (.xlsx / .xls)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from app.core.readers.tabular import tabular_read_outputs


def list_excel_sheets(path: Path) -> list[str]:
    book = pd.ExcelFile(path)
    return list(book.sheet_names)


def read_excel_file(
    path: Path,
    *,
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Fichier Excel introuvable: {path}")

    sheets = list_excel_sheets(path)
    if not sheets:
        raise ValueError("Fichier Excel sans feuille lisible.")

    active = sheet_name or sheets[0]
    if active not in sheets:
        raise ValueError(
            f"Feuille « {active} » absente. Feuilles disponibles : {', '.join(sheets)}.",
        )

    df = pd.read_excel(path, sheet_name=active, engine=None)
    if df.empty:
        df = pd.DataFrame()

    return tabular_read_outputs(
        df,
        source="excel",
        path=str(path),
        extra_meta={"sheet_name": active, "sheets": sheets},
    )
