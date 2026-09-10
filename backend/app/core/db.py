"""Accès PostGIS et bootstrap du schéma gix (idempotent)."""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import settings

_engine: Optional[Engine] = None

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE SCHEMA IF NOT EXISTS gix;
CREATE SCHEMA IF NOT EXISTS gix_output;
CREATE SCHEMA IF NOT EXISTS samples;

CREATE TABLE IF NOT EXISTS gix.workflows (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    definition JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gix.executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_id UUID REFERENCES gix.workflows(id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMP,
    logs TEXT
);

CREATE TABLE IF NOT EXISTS gix.node_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id UUID NOT NULL REFERENCES gix.executions(id) ON DELETE CASCADE,
    node_id VARCHAR(128) NOT NULL,
    input_snapshot JSONB,
    output_snapshot JSONB,
    execution_time_ms INTEGER,
    UNIQUE (execution_id, node_id)
);

CREATE INDEX IF NOT EXISTS gix_executions_workflow_idx ON gix.executions (workflow_id);
CREATE INDEX IF NOT EXISTS gix_executions_status_idx ON gix.executions (status);
CREATE INDEX IF NOT EXISTS gix_snapshots_execution_idx ON gix.node_snapshots (execution_id);
"""


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.sqlalchemy_url, pool_pre_ping=True)
    return _engine


def ensure_schema() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for statement in [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]:
            conn.execute(text(statement))


def json_param(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def as_uuid(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    return UUID(str(value))


def new_uuid() -> str:
    return str(uuid4())
