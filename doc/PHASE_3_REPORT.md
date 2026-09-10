# Rapport Phase 3 — BIM (IFC/DXF), Raster GeoTIFF et connecteurs WFS/API

## 1. Nouveaux nœuds

| Type | Catégorie | Bibliothèque | Rôle |
|---|---|---|---|
| `ifc_bim_reader` | Reader | `ifcopenshell` | Parse IFC, Psets, empreintes / centroïdes GeoJSON |
| `dxf_reader` | Reader | `ezdxf` | LINES / POLYLINES / HATCH → vecteur + calques |
| `geotiff_raster_reader` | Reader | `rasterio` | GeoTIFF (satellite, ortho, MNT) + preview PNG Base64 |
| `rest_wfs_reader` | Reader | `httpx` | WFS 2.0 paginé, REST GeoJSON, Overpass, Bearer, cache |
| `raster_clipper` | Transformer | `rasterio.mask` | Input A raster × Input B polygone → GeoTIFF découpé |
| `zonal_statistics` | Transformer | `rasterstats` | min / max / mean d'un MNT sur une couche vectorielle |

Les Writers métier continuent d'écrire dans `gix_output`.

## 2. Dépendances

Backend (`requirements.txt`) : `ifcopenshell`, `ezdxf`, `rasterio`, `rasterstats`, `pillow`, `numpy`.

Frontend (`package.json`) : `deck.gl`, `@deck.gl/core`, `@deck.gl/layers`, `@deck.gl/mapbox`.

Image backend : paquets système GDAL/PROJ/GEOS conservés pour les outils CLI. Les variables `PROJ_LIB` / `GDAL_DATA` **ne sont pas** forcées vers `/usr/share/proj`, afin d'éviter le conflit `proj.db LAYOUT.VERSION` entre PROJ Debian et les wheels manylinux de `rasterio` / `ifcopenshell`.

## 3. Frontend

- **MapViewer** : bascule **2D / 3D BIM**. En 3D, pitch MapLibre + extrusion Deck.gl (`height` / `Elevation`).
- **Inspecteur** : onglet **Raster** affichant la dalle PNG Base64 (Input / Output).

## 4. Jeux d'exemple & workflow démo

Au démarrage FastAPI (`app/samples/bootstrap.py`) :

- `/workspace/samples/sample.ifc`
- `/workspace/samples/sample.dxf`
- `/workspace/samples/sample_dem.tif`
- Workflow persisté **IFC → Lambert-93 → PostGIS** (`gix.workflows`)

Définition versionnée : `doc/examples/ifc_reproject_postgis.json`.

Enchaînement : `ifc_bim_reader` → `reproject` (EPSG:4326 → EPSG:2154) → `postgis_writer` (`gix_output.bim_elements`).

## 5. Démarrage

```bash
cd 4gix/docker
docker compose up --build
```

UI : http://localhost:5173 — charger le workflow d'exemple, basculer la carte en 3D après exécution.
