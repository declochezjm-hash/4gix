from __future__ import annotations

from typing import Any, Dict

from app.nodes.base import Base4GIxNode
from app.nodes.workflow_features import input_features


class ComposerAgentNode(Base4GIxNode):
    """Nœud de conception : l'agent remplace ce nœud (et optionnellement l'aval) par un sous-graphe."""

    node_type = "composer_agent"
    category = "Transformer"
    is_spatial = True
    label = "Composer Agent"
    description = (
        "Décrivez une transformation en langage naturel ; l'agent propose des nœuds "
        "qui remplacent ce bloc à l'acceptation."
    )
    input_handles = ["input"]
    output_handles = ["output"]
    palette_group = "Agents"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Composer Agent",
            "description": cls.description,
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "title": "Instruction",
                    "default": "",
                },
                "replace_downstream": {
                    "type": "boolean",
                    "title": "Remplacer aussi les nœuds en aval",
                    "description": (
                        "Si activé, le nœud Composer et toute la chaîne sortante "
                        "sont remplacés par le graphe proposé."
                    ),
                    "default": True,
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        features = input_features(inputs)
        return {
            "items": features,
            "metadata": {
                "composer_agent": True,
                "note": "Passthrough — configurez via l'agent puis Accept.",
            },
        }
