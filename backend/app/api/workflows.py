from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core import persistence

router = APIRouter(prefix="/api", tags=["workflows"])


class WorkflowSpec(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1)
    definition: Dict[str, Any] = Field(default_factory=dict)


@router.get("/workflows")
def list_workflows() -> Dict[str, Any]:
    items = persistence.list_workflows()
    return {"count": len(items), "workflows": items}


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str) -> Dict[str, Any]:
    item = persistence.get_workflow(workflow_id)
    if not item:
        raise HTTPException(status_code=404, detail="Workflow introuvable.")
    return item


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str) -> Dict[str, Any]:
    if not persistence.delete_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow introuvable.")
    return {"ok": True, "id": workflow_id}


@router.post("/workflows")
def save_workflow(spec: WorkflowSpec) -> Dict[str, Any]:
    try:
        return persistence.upsert_workflow(
            name=spec.name,
            definition=spec.definition,
            workflow_id=spec.id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
