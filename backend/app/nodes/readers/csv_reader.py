from __future__ import annotations

from typing import Any, Dict

from app.core.paths import resolve_workspace_path
from app.core.readers.csv_reader import read_csv_file
from app.nodes.base import Base4GIxNode


class CsvReader(Base4GIxNode):
    node_type = "csv_reader"
    category = "Reader"
    is_spatial = True
    label = "CSV Reader"
    description = "Parse tabular text files with custom delimiters"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "CSV Reader",
            "description": "Détecte séparateur et encodage ; carte si colonnes X/Y ou lon/lat.",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier CSV",
                },
                "encoding": {
                    "type": "string",
                    "title": "Encodage",
                    "description": "Vide = détection automatique (UTF-8, ISO-8859-1, …).",
                },
                "delimiter": {
                    "type": "string",
                    "title": "Séparateur",
                    "description": "Un caractère. Vide = détection (, ; tab).",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        path = resolve_workspace_path(params.get("path"))
        encoding = (params.get("encoding") or "").strip() or None
        delimiter = (params.get("delimiter") or "").strip() or None
        if delimiter and len(delimiter) > 1:
            delimiter = delimiter[0]
        return read_csv_file(path, encoding=encoding, delimiter=delimiter)
