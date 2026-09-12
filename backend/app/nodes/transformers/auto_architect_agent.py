from __future__ import annotations

from typing import Any, Dict

from app.nodes.base import Base4GIxNode
from app.nodes.workflow_features import input_features


class AutoArchitectAgentNode(Base4GIxNode):
    """Agent autonome multi-étapes : plan step-by-step via step-architect."""

    node_type = "auto_architect_agent"
    category = "Transformer"
    is_spatial = True
    label = "Auto-Architect Agent"
    description = (
        "Agent autonome multi-étapes : planifie et génère l'intégralité du pipeline "
        "nœud par nœud (Ctrl+I · mode Auto-Architecte)."
    )
    input_handles = ["input"]
    output_handles = ["output"]
    palette_group = "Agents"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Auto-Architect Agent",
            "description": cls.description,
            "type": "object",
            "properties": {
                "global_objective": {
                    "type": "string",
                    "title": "Objectif global",
                    "default": "",
                },
                "auto_advance": {
                    "type": "boolean",
                    "title": "Avancement automatique",
                    "description": (
                        "Si activé, enchaîne les étapes sans attendre chaque validation "
                        "(expérimental)."
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
                "auto_architect_agent": True,
                "note": "Configurez via le Composer (Ctrl+I) · Auto-Architecte.",
            },
        }
