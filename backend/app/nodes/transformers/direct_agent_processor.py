from __future__ import annotations

from typing import Any, Dict

from app.nodes.base import Base4GIxNode
from app.nodes.workflow_features import input_features


class DirectAgentProcessorNode(Base4GIxNode):
    """Transformation spatiale directe via LLM (sans sous-graphe)."""

    node_type = "direct_agent_processor"
    category = "Transformer"
    is_spatial = True
    label = "AI Direct Processor"
    description = (
        "Exécute du code GeoPandas généré à la volée à partir d'instructions en langage naturel."
    )
    input_handles = ["input"]
    output_handles = ["output"]
    palette_group = "Intelligence Artificielle"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "AI Direct Processor",
            "description": cls.description,
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "title": "Dernière instruction",
                    "default": "",
                },
                "chat_history": {
                    "type": "array",
                    "title": "Historique tchat",
                    "default": [],
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        features = input_features(inputs)
        return {
            "items": features,
            "metadata": {
                "direct_agent_processor": True,
                "note": "Utilisez Exécuter sur le canvas ou l'onglet Tchat Direct.",
            },
        }
