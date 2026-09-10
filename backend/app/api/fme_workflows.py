from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from app.core import persistence
from app.core.config import settings
from app.core.fme_project_parser import export_fmw, parse_fmw_bytes
from app.core.fme_runner import FmeRunnerError, fme_executable_path, run_fmw_workspace

router = APIRouter(prefix="/api/v1", tags=["fme-workflows"])


@router.get("/workflows/fme-engine")
def fme_engine_status() -> Dict[str, Any]:
    """Optionnel — 4GIx n'exige pas FME pour exécuter l'ETL importé."""
    exe = fme_executable_path()
    return {
        "required": False,
        "configured": bool(exe),
        "executable": exe or None,
        "execution_default": "4gix_native",
        "hint": (
            "L'exécution standard se fait via le moteur 4GIx (Execute workflow). "
            "FME Desktop n'est requis que pour convertir un .fmw opaque une seule fois."
        ),
    }


@router.post("/workflows/import-fmw")
async def import_fmw(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith((".fmw", ".fmwt")):
        raise HTTPException(
            status_code=400,
            detail="Fichier attendu: extension .fmw ou .fmwt",
        )
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    try:
        payload = parse_fmw_bytes(raw, default_name=file.filename.rsplit(".", 1)[0])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload["filename"] = file.filename
    return payload


@router.post("/workflows/execute-fmw")
async def execute_fmw(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Optionnel : exécution fme.exe si installé (non requis pour 4GIx)."""
    if not file.filename or not file.filename.lower().endswith((".fmw", ".fmwt")):
        raise HTTPException(status_code=400, detail="Fichier attendu: .fmw ou .fmwt")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Fichier vide.")

    workspace = Path(settings.workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    safe_name = file.filename.replace("\\", "_").replace("/", "_")
    target = workspace / f"run-{uuid.uuid4().hex[:10]}-{safe_name}"
    target.write_bytes(raw)

    try:
        try:
            return {
                **run_fmw_workspace(target),
                "name": file.filename.rsplit(".", 1)[0],
                "source": "fme_engine",
            }
        except FmeRunnerError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(
                status_code=504,
                detail="Exécution FME expirée (timeout).",
            ) from exc
    finally:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass


@router.get("/workflows/{workflow_id}/export-fmw")
def export_fmw_workflow(workflow_id: str) -> PlainTextResponse:
    item = persistence.get_workflow(workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="Workflow introuvable.")
    definition = item.get("definition") or {}
    content = export_fmw(definition, name=item.get("name") or "4GIx Export")
    filename = f"{item.get('name', 'workflow')}.fmw".replace('"', "")
    return PlainTextResponse(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
