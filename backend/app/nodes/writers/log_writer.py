from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.paths import workspace_subdir
from app.nodes.base import Base4GIxNode, _as_feature_collection, unwrap_input_data
from app.nodes.fme_features import ports_payload


class LogWriter(Base4GIxNode):
    node_type = "log_writer"
    category = "Writer"
    is_spatial = False
    label = "Log Writer"
    description = "Écrit le flux (ex. REJECTED) dans un journal JSON sous /workspace/logs."
    fme_group = "Writers"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return {
            "title": "Log Writer",
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "title": "Fichier journal",
                    "default": "rejected.json",
                },
                "label": {
                    "type": "string",
                    "title": "Libellé",
                    "default": "REJECTED",
                },
            },
        }

    def execute(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        data = unwrap_input_data(inputs)
        fc = _as_feature_collection(data) or {"type": "FeatureCollection", "features": []}
        filename = params.get("filename") or "rejected.json"
        label = params.get("label") or "REJECTED"
        logs = workspace_subdir("logs")
        path = logs / filename
        payload = {
            "label": label,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "feature_count": len(fc.get("features") or []),
            "data": fc,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        features = fc.get("features") or []
        return ports_payload(
            {"output": features},
            feature_type=self.node_type,
            extra_meta={"path": str(path), "label": label, "written": len(features)},
        )
