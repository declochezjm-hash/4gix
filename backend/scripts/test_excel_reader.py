"""Tests lecture Excel (openpyxl + repli CSV)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.readers.excel_reader import (
    find_csv_fallback_for_excel,
    is_openpyxl_import_error,
)


def test_openpyxl_error_detection() -> None:
    assert is_openpyxl_import_error(
        ImportError("Import openpyxl failed. Use pip or conda to install the openpyxl package."),
    )


def test_csv_fallback_glob(tmp_path: Path) -> None:
    excel = tmp_path / "abc123-plage.xlsx"
    excel.write_bytes(b"")
    csv = tmp_path / "abc123-plage.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    found = find_csv_fallback_for_excel(excel)
    assert found == csv.resolve()


if __name__ == "__main__":
    import tempfile

    test_openpyxl_error_detection()
    with tempfile.TemporaryDirectory() as d:
        test_csv_fallback_glob(Path(d))
    print("ok")
