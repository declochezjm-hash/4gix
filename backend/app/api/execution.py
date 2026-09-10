from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core.recflow_engine import RecflowEngine, RecflowError

router = APIRouter(prefix="/api", tags=["execution"])
engine = RecflowEngine()


class GraphSpec(BaseModel):
    """Schéma JSON du Canvas (nœuds + arêtes style n8n / React Flow)."""

    nodes: list[Dict[str, Any]] = Field(default_factory=list)
    edges: list[Dict[str, Any]] = Field(default_factory=list)
    execution_id: Optional[str] = None
    name: Optional[str] = None


@router.post("/execute")
def execute_graph(spec: GraphSpec) -> Dict[str, Any]:
    result = engine.execute(spec.model_dump())
    if result.status == "error" and not result.snapshots:
        raise HTTPException(status_code=400, detail=result.error)
    return result.to_dict()


@router.post("/validate")
def validate_graph(spec: GraphSpec) -> Dict[str, Any]:
    try:
        graph = engine.build_graph(spec.model_dump())
        order = engine.topological_order(graph)
        return {
            "valid": True,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "topological_order": order,
        }
    except RecflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.websocket("/ws/execute")
async def execute_graph_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
        await websocket.send_json({"type": "started", "payload": {"name": payload.get("name")}})

        snapshots_emitted: list[Dict[str, Any]] = []

        def capture(snapshot: Dict[str, Any]) -> None:
            snapshots_emitted.append(snapshot)

        result = engine.execute(payload, on_snapshot=capture)
        for snapshot in snapshots_emitted:
            await websocket.send_json({"type": "snapshot", "payload": snapshot})
        await websocket.send_json({"type": "completed", "payload": result.to_dict()})
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "payload": {"error": str(exc)}})
        await websocket.close()
