# Rapport de structure — Socle local 4GIx

## 1. Objectif

**4GIx** est le module ETL/ELT Cloud-Native & Géospatial (SIG/BIM) de GisForge. Cette initialisation pose un **socle technique local autonome** sous `GisForge/4gix/`, exécutable via Docker Compose, sans dépendance à un orchestrateur ML externe.

Le runtime local s’appelle **Recflow Engine** : un graphe acyclique dirigé (DAG) exécuté en Python, alimenté par un canvas visuel style n8n.

## 2. Arborescence livrée

```
GisForge/
└── 4gix/
    ├── docker/
    │   ├── docker-compose.yml
    │   └── postgis/
    │       └── init.sql
    ├── backend/
    │   ├── app/
    │   │   ├── __init__.py
    │   │   ├── main.py
    │   │   ├── core/
    │   │   │   ├── config.py
    │   │   │   ├── recflow_engine.py
    │   │   │   └── sqlsafe.py
    │   │   ├── nodes/
    │   │   │   ├── __init__.py          # registre NODE_REGISTRY
    │   │   │   ├── base.py              # Base4GIxNode + snapshots UI
    │   │   │   ├── readers/
    │   │   │   ├── transformers/
    │   │   │   └── writers/
    │   │   └── api/
    │   │       ├── execution.py         # REST + WebSocket
    │   │       └── nodes_catalog.py
    │   ├── requirements.txt
    │   └── Dockerfile
    ├── frontend/
    │   ├── src/
    │   │   ├── components/
    │   │   │   ├── Canvas/
    │   │   │   ├── NodeModal/
    │   │   │   └── MapViewer/
    │   │   ├── store/
    │   │   └── App.tsx
    │   ├── package.json
    │   └── Dockerfile
    └── doc/
        └── STRUCTURE_REPORT.md
```

## 3. Conteneurs Docker

| Service compose | `container_name` | Image / build | Port hôte | Rôle |
|---|---|---|---|---|
| `4gix-postgis` | `4gix-postgis` | `postgis/postgis:15-3.3` | `5432` | Base spatiale |
| `4gix` | `4gix` | `backend/Dockerfile` (Python 3.11 + GDAL/PROJ/GEOS) | `8000` | API FastAPI + Recflow |
| `4gix-ui` | `4gix-ui` | `frontend/Dockerfile` (Vite + React) | `5173` | Canvas visuel |

Identifiants PostGIS locaux :

- utilisateur : `4gix_user`
- mot de passe : `4gix_password`
- base : `4gix_db`

Le script `docker/postgis/init.sql` active PostGIS, crée les schémas `etl` / `samples`, une table de snapshots d’exécution, et un jeu d’exemple `samples.poi`.

## 4. Recflow Engine

Fichier : `backend/app/core/recflow_engine.py`

- Construit un `networkx.DiGraph` à partir du JSON Canvas (`nodes` + `edges`).
- Refuse tout graphe cyclique (`CyclicGraphError`).
- Ordonne l’exécution par **tri topologique**.
- Résout les entrées d’un nœud à partir des sorties des parents (handles React Flow `input` / `output`).
- Après chaque nœud, produit un **snapshot** (métadonnées + preview GeoJSON/JSON) pour les fenêtres Input / Output.

Contrat JSON attendu (aligné React Flow / n8n) :

```json
{
  "name": "canvas-run",
  "nodes": [
    { "id": "geojson_reader-1", "type": "geojson_reader", "params": { "use_sample": true } }
  ],
  "edges": [
    { "id": "e1", "source": "geojson_reader-1", "target": "buffer-1" }
  ]
}
```

## 5. Contrat des nœuds

`Base4GIxNode` (`backend/app/nodes/base.py`) impose :

- `node_type`, `category` (`Reader` | `Transformer` | `Writer`), `is_spatial`
- `get_schema()` → formulaire JSON Schema pour la fenêtre **Config**
- `execute(inputs, params)` → payload métier + snapshot UI

Catalogue initial enregistré dans `NODE_REGISTRY` :

| Type | Catégorie | Spatial | Rôle |
|---|---|---|---|
| `postgis_reader` | Reader | oui | Table / SQL PostGIS |
| `file_reader` | Reader | oui | GeoJSON, GPKG, SHP, CSV |
| `geojson_reader` | Reader | oui | GeoJSON inline + jeu d’exemple |
| `reproject` | Transformer | oui | Reprojection CRS |
| `buffer` | Transformer | oui | Tampon géométrique |
| `attribute_filter` | Transformer | non | Filtre attributaire |
| `attribute_mapper` | Transformer | non | Renommage de champs |
| `postgis_writer` | Writer | oui | Écriture table PostGIS |
| `file_writer` | Writer | oui | GeoJSON / GPKG / CSV |

## 6. API FastAPI

- `GET /health` — liveness du conteneur `4gix`
- `GET /api/nodes` — catalogue + schémas UI
- `GET /api/nodes/{node_type}` — détail d’un nœud
- `POST /api/validate` — acyclicité + ordre topologique
- `POST /api/execute` — exécution synchrone du DAG
- `WS /api/ws/execute` — exécution avec snapshots poussés au fil de l’eau

## 7. Frontend (canvas n8n)

Stack : **Vite + React 18 + TypeScript + @xyflow/react + Zustand + MapLibre GL**.

- `Canvas/` : palette de nœuds, drag & drop, graphe éditable.
- `NodeModal/` : inspecteur **3 fenêtres** — Input (parents), Config (schema), Output (snapshot + carte).
- `MapViewer/` : rendu GeoJSON via MapLibre.
- `store/dagStore.ts` : état du DAG, snapshots, lancement d’exécution.

## 8. Démarrage local

Depuis `GisForge/4gix/docker` :

```bash
docker compose up --build
```

Puis :

- UI : http://localhost:5173
- API : http://localhost:8000/docs
- PostGIS : `localhost:5432` / `4gix_db`

Flux de smoke test recommandé :

1. Ajouter un nœud **GeoJSON Reader** (jeu d’exemple activé).
2. Relier un **Buffer** puis un **PostGIS Writer** (`etl.output_layer`).
3. Cliquer sur **Exécuter le DAG**.
4. Ouvrir l’inspecteur : Input / Config / Output + carte MapLibre.

## 9. Frontière GisForge / 4GIx

GisForge (Angular + Supabase) reste l’application hôte. **4GIx** est un socle Docker isolé, prêt à être branché ultérieurement (SSO, catalogues d’organisations, stockage cloud). Aucune modification n’a été portée sur le code Angular existant dans cette étape.
