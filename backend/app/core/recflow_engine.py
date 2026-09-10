"""
Recflow Engine — orchestrateur DAG local de 4GIx.

Exécute un graphe acyclique (style n8n) transmis en JSON par le Canvas.
Utilise networkx pour la validation d'acyclicité et le tri topologique.
Aucun orchestrateur ML externe n'est utilisé.
"""

from __future__ import annotations

import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import networkx as nx

from app.nodes import get_node_class
from app.nodes.base import NodeSnapshot, build_snapshot_from_payload


class RecflowError(Exception):
    """Erreur d'orchestration Recflow."""


class CyclicGraphError(RecflowError):
    """Le graphe contient un cycle."""


class UnknownNodeTypeError(RecflowError):
    """Type de nœud absent du registre."""


class MissingNodeError(RecflowError):
    """Référence de nœud introuvable dans le graphe."""


SnapshotCallback = Callable[[Dict[str, Any]], None]


@dataclass
class ExecutionResult:
    execution_id: str
    status: str
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "snapshots": self.snapshots,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "node_count": len(self.snapshots),
        }


class RecflowEngine:
    """Runtime DAG sur-mesure pour le Canvas 4GIx."""

    def build_graph(self, spec: Dict[str, Any]) -> nx.DiGraph:
        nodes = spec.get("nodes") or []
        edges = spec.get("edges") or []
        graph = nx.DiGraph()

        for node in nodes:
            node_id = node.get("id")
            if not node_id:
                raise RecflowError("Chaque nœud doit posséder un identifiant `id`.")
            graph.add_node(node_id, **node)

        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                raise RecflowError("Chaque arête doit définir `source` et `target`.")
            if source not in graph:
                raise MissingNodeError(f"Nœud source introuvable: {source}")
            if target not in graph:
                raise MissingNodeError(f"Nœud cible introuvable: {target}")
            graph.add_edge(
                source,
                target,
                sourceHandle=edge.get("sourceHandle") or "output",
                targetHandle=edge.get("targetHandle") or "input",
                edge_id=edge.get("id"),
            )

        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            raise CyclicGraphError(f"Le graphe contient un cycle: {cycles[:5]}")

        return graph

    def topological_order(self, graph: nx.DiGraph) -> List[str]:
        return list(nx.topological_sort(graph))

    def _collect_inputs(self, graph: nx.DiGraph, node_id: str, outputs: Dict[str, Any]) -> Dict[str, Any]:
        inputs: Dict[str, Any] = {}
        for predecessor in graph.predecessors(node_id):
            edge_data = graph.get_edge_data(predecessor, node_id) or {}
            handle = edge_data.get("targetHandle") or "input"
            parent_output = outputs.get(predecessor, {})
            # Un handle déjà présent agrège les parents en liste
            if handle in inputs:
                existing = inputs[handle]
                if not isinstance(existing, list):
                    existing = [existing]
                existing.append(parent_output)
                inputs[handle] = existing
            else:
                inputs[handle] = parent_output
        return inputs

    def execute(
        self,
        spec: Dict[str, Any],
        on_snapshot: Optional[SnapshotCallback] = None,
    ) -> ExecutionResult:
        execution_id = spec.get("execution_id") or str(uuid.uuid4())
        started = time.perf_counter()
        snapshots: List[Dict[str, Any]] = []
        outputs: Dict[str, Any] = {}

        try:
            graph = self.build_graph(spec)
        except RecflowError as exc:
            result = ExecutionResult(
                execution_id=execution_id,
                status="error",
                error=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
            )
            return result

        order = self.topological_order(graph)

        for node_id in order:
            node_def = graph.nodes[node_id]
            node_type = node_def.get("type") or node_def.get("data", {}).get("nodeType")
            params = node_def.get("params")
            if params is None:
                params = (node_def.get("data") or {}).get("params") or {}

            node_started = time.perf_counter()
            try:
                node_cls = get_node_class(node_type)
            except KeyError as exc:
                snapshot = NodeSnapshot(
                    node_id=node_id,
                    node_type=str(node_type),
                    status="error",
                    duration_ms=round((time.perf_counter() - node_started) * 1000, 3),
                    error=str(exc),
                ).to_dict()
                snapshots.append(snapshot)
                if on_snapshot:
                    on_snapshot(snapshot)
                return ExecutionResult(
                    execution_id=execution_id,
                    status="error",
                    snapshots=snapshots,
                    outputs=outputs,
                    error=str(exc),
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                )

            inputs = self._collect_inputs(graph, node_id, outputs)
            instance = node_cls()

            try:
                payload = instance.execute(inputs=inputs, params=params) or {}
                duration_ms = round((time.perf_counter() - node_started) * 1000, 3)
                snapshot = payload.get("snapshot") or build_snapshot_from_payload(
                    node_id=node_id,
                    node_type=node_cls.node_type,
                    payload=payload,
                    duration_ms=duration_ms,
                    category=node_cls.category,
                    is_spatial=node_cls.is_spatial,
                )
                if "duration_ms" not in snapshot or snapshot.get("duration_ms") is None:
                    snapshot["duration_ms"] = duration_ms
                snapshot["node_id"] = node_id
                snapshot["status"] = snapshot.get("status") or "success"
                outputs[node_id] = payload
                snapshots.append(snapshot)
                if on_snapshot:
                    on_snapshot(snapshot)
            except Exception as exc:  # noqa: BLE001 — surface d'erreur runtime des nœuds
                duration_ms = round((time.perf_counter() - node_started) * 1000, 3)
                snapshot = NodeSnapshot(
                    node_id=node_id,
                    node_type=node_cls.node_type,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(exc),
                    metadata={"traceback": traceback.format_exc()},
                ).to_dict()
                snapshots.append(snapshot)
                if on_snapshot:
                    on_snapshot(snapshot)
                return ExecutionResult(
                    execution_id=execution_id,
                    status="error",
                    snapshots=snapshots,
                    outputs=outputs,
                    error=f"Échec du nœud `{node_id}` ({node_cls.node_type}): {exc}",
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                )

        return ExecutionResult(
            execution_id=execution_id,
            status="success",
            snapshots=snapshots,
            outputs=outputs,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
