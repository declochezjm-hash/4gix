from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.core import persistence
from app.core.recflow_engine import RecflowEngine, RecflowError

router = APIRouter(prefix="/api", tags=["execution"])
engine = RecflowEngine()


class GraphSpec(BaseModel):
    """Schéma JSON du Canvas (nœuds + arêtes style n8n / React Flow)."""

    nodes: list[Dict[str, Any]] = Field(default_factory=list)
    edges: list[Dict[str, Any]] = Field(default_factory=list)
    execution_id: Optional[str] = None
    workflow_id: Optional[str] = None
    name: Optional[str] = None


@router.post("/execute")
def execute_graph(spec: GraphSpec) -> Dict[str, Any]:
    result = engine.execute(spec.model_dump())
    if result.status == "FAILED" and not result.snapshots:
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


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str) -> Dict[str, Any]:
    item = persistence.get_execution(execution_id)
    if not item:
        raise HTTPException(status_code=404, detail="Exécution introuvable.")
    return item


@router.get("/executions/{execution_id}/snapshots/{node_id}")
def get_execution_snapshot(execution_id: str, node_id: str) -> Dict[str, Any]:
    item = persistence.get_node_snapshot(execution_id, node_id)
    if not item:
        raise HTTPException(status_code=404, detail="Snapshot introuvable pour ce nœud.")
    return item


@router.websocket("/ws/execute")
async def execute_graph_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        payload = await websocket.receive_json()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

        def emit(event: Dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(queue.put(event), loop)

        def run() -> None:
            def on_start(node_id: str) -> None:
                emit({"type": "node_running", "payload": {"node_id": node_id, "status": "RUNNING"}})

            def on_snapshot(snapshot: Dict[str, Any]) -> None:
                emit({"type": "snapshot", "payload": snapshot})

            result = engine.execute(payload, on_snapshot=on_snapshot, on_node_start=on_start)
            event_type = "completed" if result.status == "COMPLETED" else "failed"
            emit({"type": event_type, "payload": result.to_dict()})

        await websocket.send_json(
            {
                "type": "started",
                "payload": {
                    "name": payload.get("name"),
                    "workflow_id": payload.get("workflow_id"),
                    "status": "RUNNING",
                },
            }
        )
        worker = loop.run_in_executor(None, run)
        while True:
            if worker.done() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.15)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                continue
        await worker
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json({"type": "error", "payload": {"error": str(exc), "status": "FAILED"}})
        except Exception:  # noqa: BLE001
            pass
        await websocket.close()
