"""Exécution d'un workspace .fmw via le moteur FME Desktop (fme.exe)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings


class FmeRunnerError(ValueError):
    """Erreur d'exécution ou de configuration FME."""


def fme_executable_path() -> str | None:
    raw = (settings.fme_executable or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        return str(path)
    return raw


def run_fmw_workspace(fmw_path: Path, *, timeout_sec: int = 7200) -> Dict[str, Any]:
    exe = fme_executable_path()
    if not exe:
        raise FmeRunnerError(
            "Moteur FME non configuré. Définissez FOURGIX_FME_EXECUTABLE "
            "(ex. C:\\Program Files\\FME\\fme.exe) sur la machine qui héberge l'API."
        )
    if not fmw_path.is_file():
        raise FmeRunnerError(f"Fichier introuvable: {fmw_path}")

    proc = subprocess.run(
        [exe, str(fmw_path)],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        check=False,
    )
    log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    status = "COMPLETED" if proc.returncode == 0 else "FAILED"
    return {
        "status": status,
        "exit_code": proc.returncode,
        "log": log[-120_000:],
        "fmw_path": str(fmw_path),
    }
