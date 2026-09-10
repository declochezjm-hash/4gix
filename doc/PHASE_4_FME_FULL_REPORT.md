# Rapport Phase 4 — Moteur FME avancé et catalogue complet des Transformers

## 1. Objectif

La Phase 3 (BIM / raster / WFS) est conservée. La Phase 4 aligne 4GIx sur **FME Workbench** :

- moteur Recflow **multi-ports** (`PASSED`, `FAILED`, `REJECTED`, `UNMERGED_*`, etc.) ;
- métadonnées d'entité FME (`fme_feature_type`, `fme_geometry`, `fme_crs`, `fme_rejection_code`) ;
- catalogue complet des transformers demandés ;
- inspecteur type **FME Data Inspector** (structure + attributs + surbrillance MapLibre).

Version API : **0.4.0**.

## 2. Contrat Recflow & Feature Handling

Fichier central : `backend/app/nodes/fme_features.py`.

Chaque payload vectoriel suit :

```json
{
  "data": { "type": "FeatureCollection", "features": [] },
  "ports": { "output": {}, "rejected": {} },
  "metadata": { "fme_ports": true, "port_counts": {}, "crs": "EPSG:4326" }
}
```

`RecflowEngine._collect_inputs` résout `sourceHandle` → port parent via `extract_port`, puis injecte le flux sur `targetHandle`. Les nœuds `etl` du canvas utilisent `data.nodeType` comme type réel.

`Base4GIxNode` expose désormais `output_handles` et `fme_group` dans `catalog_entry()`.

## 3. Catalogue des transformers FME

Tous les nœuds ci-dessous sont enregistrés dans `NODE_REGISTRY`. Les nœuds historiques (`buffer`, `reproject`, `attribute_filter`, `spatial_join`…) restent disponibles.

### A. Geometry & Quality

| `node_type` | Équivalent FME | Ports |
|---|---|---|
| `geometry_validator` | GeometryValidator | `output`, `rejected` |
| `geometry_filter` | GeometryFilter | `point`, `linestring`, `polygon`, `multipolygon`, `null` |
| `snapper` | Snapper | `output` |
| `orientor` | Orientor | `output` |

Réparation : `shapely.validation.make_valid`. Les géométries nulles / irréparables partent sur `<REJECTED>`.

### B. Spatial Analysis

| `node_type` | Équivalent FME | Ports / poignées |
|---|---|---|
| `bufferer` | Bufferer | cap round / flat / square, distance en mètres (Lambert-93) |
| `clipper` | Clipper | in `input`+`clipper` → `inside` / `outside` |
| `dissolver` | Dissolver | groupement attributaire |
| `area_on_area_overlayer` | AreaOnAreaOverlayer | ids d'origine `_overlay_ids` |
| `line_on_line_overlayer` | LineOnLineOverlayer | nœuds aux intersections |
| `centroid_extractor` | CenterPointReplacer | centroïde / point intérieur |
| `bounding_box_replacer` | BoundingBoxReplacer | envelope |
| `densifier` | Densifier | `segmentize` en mètres |
| `generalizer` | DouglasPeucker / Generalizer | `simplify` |

### C. Combiners & Joins

| `node_type` | Équivalent FME | Ports |
|---|---|---|
| `feature_merger` | FeatureMerger | `merged`, `unmerged_request`, `unmerged_supplier` |
| `spatial_relator` | SpatialFilter / SpatialRelator | DE-9IM → `related` / `unrelated` |
| `neighbor_finder` | NeighborFinder | K plus proches voisins (`sjoin_nearest`) |

### D. Attribute Operations

| `node_type` | Équivalent FME | Ports |
|---|---|---|
| `attribute_manager` | AttributeManager | create / rename / delete / type / expr Python restreinte |
| `tester` | Tester | `passed` / `failed` (AND/OR) |
| `test_filter` | TestFilter | `output1`…`output3` + `else` |
| `list_exploder` | ListExploder | explosion de listes |
| `counter` | Counter | identifiant séquentiel |
| `duplicate_filter` | DuplicateFilter | `unique` / `duplicate` |

### E. Coordinate Systems

| `node_type` | Équivalent FME | Rôle |
|---|---|---|
| `reprojector` | Reprojector | PyProj, détection des unités degrés → mètres |

Writer additionnel : **`log_writer`** (journal JSON sous `/workspace/logs/`, destiné au flux `REJECTED`).

## 4. Canvas multi-ports (React Flow)

- `EtlNode` affiche dynamiquement les poignées d'entrée **et** de sortie nommées.
- Labels FME : Input, Output, Passed, Failed, Rejected, Unmerged_Request, Unmerged_Supplier, Inside / Outside, etc.
- Palette groupée par `fme_group` (Geometry & Quality, Spatial Analysis, Combiners & Joins, Attribute Operations, Coordinate Systems).

## 5. FME Data Inspector

Volets Input / Output :

- sélecteur de **port** si le snapshot est multi-flux ;
- onglet **FME Data Inspector** : type de géométrie, bounding box `[Xmin, Ymin, Xmax, Ymax]`, nombre de sommets, code EPSG ;
- tableau d'attributs filtrable ;
- clic sur une ligne → **surbrillance jaune** de l'entité sur MapLibre GL.

## 6. Workflow de démonstration

Nom persisté : **`FME : Validator → Tester → Dissolver → PostGIS`**.

Chaîne :

`GeoJSON Reader` (`fme_demo`) → `GeometryValidator` (`rejected` → `Log Writer`) → `Tester` (`PASSED`) → `AttributeManager` → `Dissolver` → `PostGIS Writer` (`gix_output.fme_dissolved`).

Jeu d'exemple : `/workspace/samples/fme_demo.geojson` (polygones urbains adjacents + bowtie + géométrie nulle).

Définition versionnée : `doc/examples/fme_validator_tester_dissolver.json`.

Le workflow Phase 3 **IFC → Lambert-93 → PostGIS** reste seedé.

## 7. Démarrage

```bash
cd 4gix/docker
docker compose up --build
```

- UI : http://localhost:5173
- API : http://localhost:8000/docs
- Santé : http://localhost:8000/health
- Catalogue : http://localhost:8000/api/nodes

Charger le workflow FME dans la palette Workflows, exécuter, ouvrir GeometryValidator : port `rejected` vers le journal, port `output` vers Tester. Dans l'inspecteur, l'onglet FME Data Inspector liste les attributs `fme_*` et met en surbrillance l'entité cliquée.

## 8. Fichiers clés

| Zone | Fichiers |
|---|---|
| Moteur | `backend/app/core/recflow_engine.py`, `backend/app/nodes/base.py`, `backend/app/nodes/fme_features.py` |
| Transformers | `backend/app/nodes/transformers/{geometry_quality,spatial_analysis,combiners,attributes,coordinates}.py` |
| Writer log | `backend/app/nodes/writers/log_writer.py` |
| Canvas / inspecteur | `frontend/src/components/Canvas/EtlNode.tsx`, `NodePalette.tsx`, `NodeModal/DataPane.tsx`, `MapViewer/MapViewer.tsx` |
| Seed | `backend/app/samples/bootstrap.py` |
