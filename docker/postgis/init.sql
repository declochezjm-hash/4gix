-- 4GIx local PostGIS bootstrap
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS samples;

-- Catalogue interne des exécutions DAG
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

-- Jeu d'exemple spatial (points d'intérêt, Lambert-93 + WGS84)
CREATE TABLE IF NOT EXISTS samples.poi (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    city TEXT NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);

INSERT INTO samples.poi (name, category, city, geom) VALUES
    ('Tour Eiffel', 'monument', 'Paris', ST_SetSRID(ST_MakePoint(2.2945, 48.8584), 4326)),
    ('Notre-Dame', 'monument', 'Paris', ST_SetSRID(ST_MakePoint(2.3499, 48.8529), 4326)),
    ('Vieux-Port', 'port', 'Marseille', ST_SetSRID(ST_MakePoint(5.3698, 43.2965), 4326)),
    ('Place Bellecour', 'place', 'Lyon', ST_SetSRID(ST_MakePoint(4.8320, 45.7578), 4326)),
    ('Capitole', 'monument', 'Toulouse', ST_SetSRID(ST_MakePoint(1.4442, 43.6045), 4326)),
    ('Château des Ducs', 'monument', 'Nantes', ST_SetSRID(ST_MakePoint(-1.5503, 47.2163), 4326)),
    ('Place Stanislas', 'place', 'Nancy', ST_SetSRID(ST_MakePoint(6.1834, 48.6936), 4326)),
    ('Palais Rohan', 'monument', 'Strasbourg', ST_SetSRID(ST_MakePoint(7.7530, 48.5803), 4326));

CREATE INDEX IF NOT EXISTS poi_geom_idx ON samples.poi USING GIST (geom);

GRANT USAGE ON SCHEMA etl TO 4gix_user;
GRANT USAGE ON SCHEMA samples TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA etl TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA samples TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA samples TO 4gix_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA etl TO 4gix_user;
