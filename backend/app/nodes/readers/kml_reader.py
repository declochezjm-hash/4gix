from __future__ import annotations

from typing import Any, Dict

from app.core.paths import resolve_workspace_path
from app.core.readers.kml_reader import read_kml_file
from app.nodes.base import Base4GIxNode


class KmlReader(Base4GIxNode):
    node_type = "kml_reader"
    category = "Reader"
    is_spatial = True
    label = "KML / KMZ Reader"
    description = "Read Google Earth vector data"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "KML / KMZ Reader",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier .kml ou .kmz",
                },
                "layer": {
                    "type": "string",
                    "title": "Couche (optionnel)",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        path = resolve_workspace_path(params.get("path"))
        layer = (params.get("layer") or "").strip() or None
        return read_kml_file(path, layer=layer)
