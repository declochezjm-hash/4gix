"""Persistance des workflows, exécutions et snapshots Recflow."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.core.db import as_uuid, get_engine, json_param, new_uuid


def list_workflows() -> List[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, name, definition, created_at, updated_at
                FROM gix.workflows
                ORDER BY updated_at DESC
                """
            )
        )
        return [_workflow_row(row) for row in rows.mappings()]


def get_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, definition, created_at, updated_at
                FROM gix.workflows
                WHERE id = :id
                """
            ),
            {"id": as_uuid(workflow_id)},
        ).mappings().first()
        return _workflow_row(row) if row else None


def upsert_workflow(
    name: str,
    definition: Dict[str, Any],
    workflow_id: Optional[str] = None,
) -> Dict[str, Any]:
    engine = get_engine()
    existing = get_workflow(workflow_id) if workflow_id else None
    with engine.begin() as conn:
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE gix.workflows
                    SET name = :name,
                        definition = CAST(:definition AS jsonb),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": as_uuid(workflow_id),
                    "name": name,
                    "definition": json_param(definition),
                },
            )
            saved_id = workflow_id
        else:
            saved_id = workflow_id or new_uuid()
            conn.execute(
                text(
                    """
                    INSERT INTO gix.workflows (id, name, definition)
                    VALUES (:id, :name, CAST(:definition AS jsonb))
                    """
                ),
                {
                    "id": as_uuid(saved_id),
                    "name": name,
                    "definition": json_param(definition),
                },
            )
    saved = get_workflow(saved_id)
    if not saved:
        raise RuntimeError("Échec de sauvegarde du workflow.")
    return saved


def delete_workflow(workflow_id: str) -> bool:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM gix.workflows WHERE id = :id"),
            {"id": as_uuid(workflow_id)},
        )
    return bool(result.rowcount)


def create_execution(
    execution_id: str,
    workflow_id: Optional[str] = None,
    status: str = "RUNNING",
) -> None:
    engine = get_engine()
    wf = as_uuid(workflow_id) if workflow_id else None
    if wf and get_workflow(workflow_id) is None:
        wf = None
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gix.executions (id, workflow_id, status, started_at, logs)
                VALUES (:id, :workflow_id, :status, NOW(), :logs)
                ON CONFLICT (id) DO UPDATE
                    SET status = EXCLUDED.status,
                        started_at = NOW(),
                        finished_at = NULL,
                        logs = EXCLUDED.logs
                """
            ),
            {
                "id": as_uuid(execution_id),
                "workflow_id": wf,
                "status": status,
                "logs": "",
            },
        )


def append_execution_log(execution_id: str, line: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE gix.executions
                SET logs = COALESCE(logs, '') || :line
                WHERE id = :id
                """
            ),
            {"id": as_uuid(execution_id), "line": line if line.endswith("\n") else line + "\n"},
        )


def finish_execution(execution_id: str, status: str, logs: Optional[str] = None) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE gix.executions
                SET status = :status,
                    finished_at = NOW(),
                    logs = CASE WHEN :logs IS NULL THEN logs ELSE :logs END
                WHERE id = :id
                """
            ),
            {"id": as_uuid(execution_id), "status": status, "logs": logs},
        )


def upsert_node_snapshot(
    execution_id: str,
    node_id: str,
    input_snapshot: Any,
    output_snapshot: Any,
    execution_time_ms: int,
) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gix.node_snapshots (
                    execution_id, node_id, input_snapshot, output_snapshot, execution_time_ms
                )
                VALUES (
                    :execution_id, :node_id,
                    CAST(:input_snapshot AS jsonb),
                    CAST(:output_snapshot AS jsonb),
                    :execution_time_ms
                )
                ON CONFLICT (execution_id, node_id) DO UPDATE
                    SET input_snapshot = EXCLUDED.input_snapshot,
                        output_snapshot = EXCLUDED.output_snapshot,
                        execution_time_ms = EXCLUDED.execution_time_ms
                """
            ),
            {
                "execution_id": as_uuid(execution_id),
                "node_id": node_id,
                "input_snapshot": json_param(input_snapshot),
                "output_snapshot": json_param(output_snapshot),
                "execution_time_ms": int(execution_time_ms),
            },
        )


def get_execution(execution_id: str) -> Optional[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, workflow_id, status, started_at, finished_at, logs
                FROM gix.executions
                WHERE id = :id
                """
            ),
            {"id": as_uuid(execution_id)},
        ).mappings().first()
        if not row:
            return None
        snapshots = conn.execute(
            text(
                """
                SELECT node_id, input_snapshot, output_snapshot, execution_time_ms
                FROM gix.node_snapshots
                WHERE execution_id = :id
                ORDER BY execution_time_ms NULLS LAST
                """
            ),
            {"id": as_uuid(execution_id)},
        )
        return {
            "id": str(row["id"]),
            "workflow_id": str(row["workflow_id"]) if row["workflow_id"] else None,
            "status": row["status"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
            "logs": row["logs"],
            "snapshots": [
                {
                    "node_id": s["node_id"],
                    "input_snapshot": s["input_snapshot"],
                    "output_snapshot": s["output_snapshot"],
                    "execution_time_ms": s["execution_time_ms"],
                }
                for s in snapshots.mappings()
            ],
        }


def get_node_snapshot(execution_id: str, node_id: str) -> Optional[Dict[str, Any]]:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT node_id, input_snapshot, output_snapshot, execution_time_ms
                FROM gix.node_snapshots
                WHERE execution_id = :execution_id AND node_id = :node_id
                """
            ),
            {"execution_id": as_uuid(execution_id), "node_id": node_id},
        ).mappings().first()
        if not row:
            return None
        return {
            "execution_id": execution_id,
            "node_id": row["node_id"],
            "input_snapshot": row["input_snapshot"],
            "output_snapshot": row["output_snapshot"],
            "execution_time_ms": row["execution_time_ms"],
        }


def _workflow_row(row: Any) -> Dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "definition": row["definition"] or {},
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }
