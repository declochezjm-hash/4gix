from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.shapefile_bundle import ShapefileIncompleteError
from app.core.workspace_export import workspace_download_payload

router = APIRouter(tags=["workspace"])


@router.get("/workspace/download")
def download_workspace_file(
    path: str = Query(..., description="Chemin logique /workspace/…"),
) -> Response:
    try:
        content, filename, media_type = workspace_download_payload(path)
    except ShapefileIncompleteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    safe_name = quote(filename)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{safe_name}",
        },
    )
