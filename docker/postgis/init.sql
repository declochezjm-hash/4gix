-- 4GIx local PostGIS bootstrap
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS samples;
CREATE SCHEMA IF NOT EXISTS gix;
CREATE SCHEMA IF NOT EXISTS gix_output;

-- Catalogue interne historique (compatibilité Phase 1)
CREATE TABLE IF NOT EXISTS etl.executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    graph_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    node_count INTEGER DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS etl.node_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_id UUID REFERENCES etl.executions(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms DOUBLE PRECISION,
    metadata JSONB,
    preview JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Workflows Canvas (Phase 2)
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

-- Jeu d'exemple spatial (points d'intérêt)
CREATE TABLE IF NOT EXISTS samples.poi (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    city TEXT NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);

INSERT INTO samples.poi (name, category, city, geom)
SELECT v.name, v.category, v.city, v.geom
FROM (
    VALUES
        ('Tour Eiffel', 'monument', 'Paris', ST_SetSRID(ST_MakePoint(2.2945, 48.8584), 4326)),
        ('Notre-Dame', 'monument', 'Paris', ST_SetSRID(ST_MakePoint(2.3499, 48.8529), 4326)),
        ('Vieux-Port', 'port', 'Marseille', ST_SetSRID(ST_MakePoint(5.3698, 43.2965), 4326)),
        ('Place Bellecour', 'place', 'Lyon', ST_SetSRID(ST_MakePoint(4.8320, 45.7578), 4326)),
        ('Capitole', 'monument', 'Toulouse', ST_SetSRID(ST_MakePoint(1.4442, 43.6045), 4326)),
        ('Château des Ducs', 'monument', 'Nantes', ST_SetSRID(ST_MakePoint(-1.5503, 47.2163), 4326)),
        ('Place Stanislas', 'place', 'Nancy', ST_SetSRID(ST_MakePoint(6.1834, 48.6936), 4326)),
        ('Palais Rohan', 'monument', 'Strasbourg', ST_SetSRID(ST_MakePoint(7.7530, 48.5803), 4326))
) AS v(name, category, city, geom)
WHERE NOT EXISTS (SELECT 1 FROM samples.poi);

CREATE INDEX IF NOT EXISTS poi_geom_idx ON samples.poi USING GIST (geom);

CREATE TABLE IF NOT EXISTS samples.regions (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL
);

INSERT INTO samples.regions (name, code, geom)
SELECT v.name, v.code, v.geom
FROM (
    VALUES
        (
            'Île-de-France',
            'IDF',
            ST_SetSRID(ST_GeomFromText('POLYGON((1.4 48.1, 3.6 48.1, 3.6 49.2, 1.4 49.2, 1.4 48.1))'), 4326)
        ),
        (
            'Auvergne-Rhône-Alpes',
            'ARA',
            ST_SetSRID(ST_GeomFromText('POLYGON((3.6 44.6, 7.2 44.6, 7.2 46.8, 3.6 46.8, 3.6 44.6))'), 4326)
        ),
        (
            'Provence-Alpes-Côte d''Azur',
            'PAC',
            ST_SetSRID(ST_GeomFromText('POLYGON((4.2 42.9, 7.8 42.9, 7.8 44.9, 4.2 44.9, 4.2 42.9))'), 4326)
        )
) AS v(name, code, geom)
WHERE NOT EXISTS (SELECT 1 FROM samples.regions);

CREATE INDEX IF NOT EXISTS regions_geom_idx ON samples.regions USING GIST (geom);

GRANT USAGE ON SCHEMA etl TO 4gix_user;
GRANT USAGE ON SCHEMA samples TO 4gix_user;
GRANT USAGE ON SCHEMA gix TO 4gix_user;
GRANT USAGE ON SCHEMA gix_output TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA etl TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA samples TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gix TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA gix_output TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA samples TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA etl TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA gix TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA gix_output TO 4gix_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA gix GRANT ALL ON TABLES TO 4gix_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA gix_output GRANT ALL ON TABLES TO 4gix_user;
