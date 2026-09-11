"""Lecture CSV avec détection séparateur et encodage."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from app.core.readers.tabular import tabular_read_outputs

ENCODINGS = ("utf-8-sig", "utf-8", "iso-8859-1", "cp1252", "latin-1")


def detect_csv_encoding(raw: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "utf-8"


def detect_csv_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        counts = {sep: sample.count(sep) for sep in (",", ";", "\t", "|")}
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else ","


def read_csv_file(
    path: Path,
    *,
    encoding: Optional[str] = None,
    delimiter: Optional[str] = None,
) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Fichier CSV introuvable: {path}")

    raw = path.read_bytes()
    chosen_encoding = encoding or detect_csv_encoding(raw)
    text = raw.decode(chosen_encoding, errors="replace")
    sample = text[:65536]
    sep = delimiter or detect_csv_delimiter(sample)

    df = pd.read_csv(path, sep=sep, encoding=chosen_encoding, engine="python")
    if df.empty:
        df = pd.DataFrame()

    return tabular_read_outputs(
        df,
        source="csv",
        path=str(path),
        extra_meta={
            "encoding": chosen_encoding,
            "delimiter": sep,
        },
    )
