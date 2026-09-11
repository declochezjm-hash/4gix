from __future__ import annotations

from typing import Any, Dict

from app.core.paths import resolve_workspace_path
from app.core.readers.excel_reader import list_excel_sheets, read_excel_file
from app.nodes.base import Base4GIxNode


class ExcelReader(Base4GIxNode):
    node_type = "excel_reader"
    category = "Reader"
    is_spatial = True
    label = "Excel Reader"
    description = "Import sheet data from .xlsx / .xls"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Excel Reader",
            "description": "Lit une feuille Excel et expose un tableau attributaire (carte si colonnes X/Y).",
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "title": "Fichier Excel",
                    "description": "Chemin dans /workspace (drag-and-drop).",
                },
                "sheet_name": {
                    "type": "string",
                    "title": "Feuille",
                    "description": "Nom de la feuille. Vide = première feuille.",
                },
            },
            "required": ["path"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        path = resolve_workspace_path(params.get("path"))
        sheet = (params.get("sheet_name") or "").strip() or None
        payload = read_excel_file(path, sheet_name=sheet)
        payload["metadata"]["available_sheets"] = list_excel_sheets(path)
        return payload
