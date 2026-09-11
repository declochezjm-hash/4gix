from __future__ import annotations

from typing import Any, Dict

from app.core.paths import resolve_workspace_path
from app.core.readers.gpkg_reader import list_gpkg_layers, read_gpkg_file
from app.nodes.base import Base4GIxNode


class GpkgReader(Base4GIxNode):
    node_type = "gpkg_reader"
    category = "Reader"
    is_spatial = True
    label = "GeoPackage Reader"
    description = "Read vector/raster layers from OGC .gpkg"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "GeoPackage Reader",
            "description": "Couche vectorielle en EPSG:4326 pour la carte.",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier .gpkg",
                },
                "layer": {
                    "type": "string",
                    "title": "Couche",
                    "description": "Nom de couche. Vide = première couche spatiale.",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        path = resolve_workspace_path(params.get("path"))
        layer = (params.get("layer") or "").strip() or None
        payload = read_gpkg_file(path, layer=layer)
        payload["metadata"]["available_layers"] = list_gpkg_layers(path)
        return payload
