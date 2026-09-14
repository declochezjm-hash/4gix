from __future__ import annotations

from typing import Any, Dict, Type

from app.nodes.base import Base4GIxNode, unwrap_input_data
from app.nodes.connectors.schemas import (
    human_approval_schema,
    integration_connector_schema,
    send_and_wait_schema,
)
from app.nodes.connectors.specs import CONNECTOR_SPECS, SEND_AND_WAIT


class HumanApprovalNode(Base4GIxNode):
    node_type = "human_approval"
    category = "Transformer"
    is_spatial = False
    label = "Human in the loop"
    description = (
        "Wait for approval or human input before continuing."
    )
    palette_group = "Approvals"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return human_approval_schema()

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        return {
            "data": data,
            "metadata": {
                "human_approval": "auto_approved_dev",
                "response_type": params.get("response_type") or "approval",
                "message": params.get("message") or "",
                "wait": {
                    "limited": bool(params.get("limit_wait_time")),
                    "amount": params.get("wait_amount"),
                    "unit": params.get("wait_unit"),
                },
            },
        }


class ConnectorNode(Base4GIxNode):
    """Connecteur d'intégration (pass-through jusqu'à implémentation complète)."""

    category = "Transformer"
    is_spatial = False
    connector_id: str = ""
    palette_group: str = "Connectors"
    _param_schema: Dict[str, Any] = {}

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        if cls._param_schema:
            return cls._param_schema
        return integration_connector_schema(cls.label or "Connecteur", cls.description)

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        return {
            "data": data,
            "metadata": {
                "connector": self.connector_id,
                "operation": params.get("operation") or "sendAndWait",
                "response_type": params.get("response_type"),
                "recipient": params.get("recipient"),
                "status": "configured_stub",
            },
        }


def build_connector_classes() -> Dict[str, Type[Base4GIxNode]]:
    registry: Dict[str, Type[Base4GIxNode]] = {}
    for spec in CONNECTOR_SPECS:
        node_type = str(spec["node_type"])
        label = str(spec["label"])
        description = str(spec.get("description") or "")
        subgroup = str(spec.get("subgroup") or "Connectors")

        if subgroup == SEND_AND_WAIT:
            schema = send_and_wait_schema(
                label,
                str(spec.get("send_wait_template") or "slack"),
                description,
                credential_type=spec.get("credential_type"),
            )
        else:
            schema = integration_connector_schema(label, description)

        class _Connector(ConnectorNode):
            pass

        _Connector.node_type = node_type
        _Connector.label = label
        _Connector.description = description
        _Connector.palette_group = subgroup
        _Connector.connector_id = str(spec["id"])
        _Connector._param_schema = schema
        _Connector.__name__ = f"Connector_{spec['id']}"
        _Connector.__qualname__ = _Connector.__name__

        registry[node_type] = _Connector
    return registry
