# Rapport Phase 2 — Inspecteur synchro, formulaires dynamiques, persistance PostGIS

## 1. Schéma PostGIS `gix`

Fichiers : `docker/postgis/init.sql` + bootstrap runtime `backend/app/core/db.py` (`ensure_schema()` au démarrage FastAPI, car un volume existant ne rejoue pas `init.sql`).

| Objet | Rôle |
|---|---|
| `gix.workflows` | DAG Canvas (`id`, `name`, `definition` JSONB React Flow, `created_at`, `updated_at`) |
| `gix.executions` | Course d'un graphe (`workflow_id` FK, `status` PENDING/RUNNING/COMPLETED/FAILED, `started_at`, `finished_at`, `logs`) |
| `gix.node_snapshots` | Snapshots par nœud (`input_snapshot`, `output_snapshot`, `execution_time_ms`) |
| `gix_output` | Schéma d'écriture métier des Writers (défaut du PostGIS Writer) |
| `samples.regions` | Polygones d'exemple pour Spatial Join |

## 2. Nouveaux endpoints

| Méthode | Chemin | Description |
|---|---|---|
| `GET` | `/api/workflows` | Liste des workflows persistés |
| `POST` | `/api/workflows` | Création ou mise à jour (si `id` fourni) |
| `GET` | `/api/workflows/{id}` | Détail + definition |
| `GET` | `/api/executions/{execution_id}` | État, logs, snapshots |
| `GET` | `/api/executions/{execution_id}/snapshots/{node_id}` | Snapshot Input/Output à chaud |
| `WS` | `/api/ws/execute` | Exécution live du DAG |

Événements WebSocket : `started` → `node_running` → `snapshot` → `completed` \| `failed`.

Le Recflow Engine persiste chaque nœud dans `gix.node_snapshots` et journalise dans `gix.executions.logs`.

## 3. Inspecteur 3 fenêtres (frontend)

- **Config** : formulaires générés depuis `GET /api/nodes` (`get_schema()`). Widgets : sélecteur EPSG, slider buffer, éditeur SQL, mapping de colonnes.
- **Input / Output** : onglets **Tableau/JSON** et **Carte SIG (MapLibre)**. Rendu GeoJSON automatique. Zoom/centre partagés (vue avant/après).
- **Canvas** : glow bleu `RUNNING`, badge vert + durée `COMPLETED`, badge rouge + message `FAILED`. Clic nœud → snapshots locaux, sinon fetch REST.

## 4. Nœud Spatial Join

`backend/app/nodes/transformers/spatial_join.py` — `SpatialJoinNode` (`spatial_join`).

- Poignées `input_a` / `input_b`.
- Prédicats GeoPandas : Intersects, Contains, Within, Touches, Overlaps.
- Démo : GeoJSON Reader (villes) + GeoJSON Reader (régions) → Spatial Join.

## 5. Vérification

```bash
cd 4gix/docker
docker compose up --build
```

Smoke test API : `GET /api/nodes` (présence de `spatial_join`), `POST /api/workflows`, `POST /api/execute` ou WS `/api/ws/execute`, puis `GET /api/executions/{id}`.
