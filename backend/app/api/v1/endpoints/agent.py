"""Endpoint Composer agentique — streaming SSE."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.composer import plan_composer
from app.agent.tools import AGENT_OPENAI_TOOLS

router = APIRouter(tags=["agent"])


class CurrentGraph(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)


class ComposerRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Instruction utilisateur (langage naturel).")
    current_graph: CurrentGraph = Field(
        default_factory=CurrentGraph,
        description="Graphe canvas courant (nœuds + edges React Flow).",
    )
    selected_node_id: Optional[str] = Field(
        default=None,
        description="Nœud sélectionné (contexte d'édition).",
    )
    context_mentions: List[str] = Field(
        default_factory=list,
        description="Références @Schema, @Input, etc.",
    )


def _sse_pack(event: Dict[str, Any]) -> str:
    event_name = str(event.get("type") or "message")
    payload = json.dumps(event, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload}\n\n"


async def _sse_stream(events: List[Dict[str, Any]]) -> AsyncIterator[str]:
    for event in events:
        yield _sse_pack(event)


@router.post("/agent/composer")
async def composer(request: ComposerRequest) -> StreamingResponse:
    """
    Agent Composer : thoughts, tool calls canvas et diffs de code en Server-Sent Events.
    """
    events = plan_composer(
        prompt=request.prompt,
        current_graph=request.current_graph.model_dump(),
        selected_node_id=request.selected_node_id,
        context_mentions=request.context_mentions,
    )
    return StreamingResponse(
        _sse_stream(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent/tools")
def list_agent_tools() -> Dict[str, Any]:
    """Schémas OpenAI Function Calling exposés par l'agent."""
    return {"count": len(AGENT_OPENAI_TOOLS), "tools": AGENT_OPENAI_TOOLS}
