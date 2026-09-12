"""Tests assemblage Shapefile (sidecars + zip uploads)."""

from __future__ import annotations

import sys
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.shapefile_bundle import (
    ShapefileIncompleteError,
    collect_shapefile_parts,
    find_matching_zip_in_uploads,
    logical_stem,
)


def _mock_uploads_dir(tmp_path: Path, monkeypatch, uploads: Path) -> None:
    def _workspace_subdir(*parts, create=False):
        if parts and parts[0] == "uploads":
            return uploads
        target = tmp_path.joinpath(*parts)
        if create:
            target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr("app.core.shapefile_bundle.workspace_subdir", _workspace_subdir)


def _write_minimal_shp(path: Path) -> None:
    path.write_bytes(b"\x00" * 100)


def test_logical_stem_strips_upload_prefix() -> None:
    assert logical_stem("a1b2c3d4e5-parcelles.shp") == "parcelles"


def test_collect_parts_from_split_uploads(tmp_path, monkeypatch) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    shp = uploads / f"{uuid.uuid4().hex[:10]}-layer.shp"
    dbf = uploads / f"{uuid.uuid4().hex[:10]}-layer.dbf"
    shx = uploads / f"{uuid.uuid4().hex[:10]}-layer.shx"
    _write_minimal_shp(shp)
    dbf.write_bytes(b"\x03")
    shx.write_bytes(b"\x00" * 100)
    _mock_uploads_dir(tmp_path, monkeypatch, uploads)

    parts = collect_shapefile_parts(shp)
    assert ".dbf" in parts and ".shx" in parts


def test_incomplete_shp_raises(tmp_path, monkeypatch) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    shp = uploads / f"{uuid.uuid4().hex[:10]}-solo.shp"
    _write_minimal_shp(shp)
    _mock_uploads_dir(tmp_path, monkeypatch, uploads)

    try:
        collect_shapefile_parts(shp)
        raise AssertionError("expected ShapefileIncompleteError")
    except ShapefileIncompleteError as exc:
        assert ".dbf" in exc.missing or ".shx" in exc.missing


def test_find_zip_in_uploads(tmp_path, monkeypatch) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    zip_path = uploads / f"{uuid.uuid4().hex[:10]}-parcelles.zip"
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("parcelles.shp", b"\x00" * 100)
        archive.writestr("parcelles.shx", b"\x00" * 100)
        archive.writestr("parcelles.dbf", b"\x03")
    zip_path.write_bytes(buffer.getvalue())
    _mock_uploads_dir(tmp_path, monkeypatch, uploads)

    found = find_matching_zip_in_uploads("parcelles")
    assert found == zip_path
