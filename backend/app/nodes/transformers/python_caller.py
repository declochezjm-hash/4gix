from __future__ import annotations

from typing import Any, Dict

from app.core.transformers.python_caller import (
    DEFAULT_CODE,
    DEFAULT_SQL,
    execute_code_transform,
)
from app.nodes.base import Base4GIxNode
from app.nodes.workflow_features import input_features


class PythonCallerNode(Base4GIxNode):
    node_type = "python_caller"
    category = "Transformer"
    is_spatial = True
    label = "Python / Code Transformer"
    description = "Éditeur de code Python (GeoPandas) ou SQL — style n8n Code node."
    output_handles = ["output", "rejected"]
    palette_group = "Core"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Python / Code Transformer",
            "description": "Code Python (GeoPandas) ou SQL (SELECT sur `items` / `gdf`).",
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "title": "Mode d'exécution",
                    "enum": ["all_items", "per_item"],
                    "enumNames": [
                        "Run Once for All Items",
                        "Run for Each Item",
                    ],
                    "default": "all_items",
                },
                "language": {
                    "type": "string",
                    "title": "Langage",
                    "enum": ["python", "sql"],
                    "enumNames": ["Python", "SQL"],
                    "default": "python",
                },
                "code": {
                    "type": "string",
                    "title": "Code",
                    "format": "code",
                    "default": DEFAULT_CODE,
                },
            },
            "required": ["code"],
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        language = (params.get("language") or "python").lower()
        default_code = DEFAULT_SQL if language == "sql" else DEFAULT_CODE
        code = (params.get("code") or default_code).strip()
        mode = (params.get("mode") or "all_items").lower()
        features = input_features(inputs)
        payload = execute_code_transform(
            node_type=self.node_type,
            features=features,
            code=code,
            mode=mode,
            language=language,
        )
        metadata = dict(payload.get("metadata") or {})
        metadata["language"] = language
        payload["metadata"] = metadata
        return payload


class CodeNode(PythonCallerNode):
    node_type = "code_node"
    label = "Code"
