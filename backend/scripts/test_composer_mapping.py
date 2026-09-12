"""Tests consignes de mappage génériques (Composer)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.composer import plan_composer


def _sample_graph() -> dict:
    return {
        "nodes": [
            {
                "id": "excel_reader-1",
                "type": "etl",
                "position": {"x": 80, "y": 160},
                "data": {
                    "label": "Excel",
                    "nodeType": "excel_reader",
                    "outputSnapshot": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {
                                    "CODE FOYER": "A1",
                                    "TYPE SUPPO": "P",
                                },
                                "geometry": None,
                            }
                        ],
                    },
                },
            }
        ],
        "edges": [],
    }


def test_generic_mapping_returns_choices() -> None:
    events = plan_composer(
        "fait un mappage",
        _sample_graph(),
        source_node_id="excel_reader-1",
        node_id="composer_agent-1",
    )
    choice_events = [e for e in events if e.get("type") == "mapping_choices"]
    assert choice_events, events
    choices = choice_events[0].get("choices") or []
    assert len(choices) == 3
    assert choices[0]["id"] == "snake_case"


def test_mapping_choice_applies_attribute_mapper() -> None:
    events = plan_composer(
        "fait un mappage",
        _sample_graph(),
        source_node_id="excel_reader-1",
        mapping_choice_id="snake_case",
    )
    summaries = [
        e.get("summary")
        for e in events
        if e.get("type") == "tool_call" and e.get("name") == "create_canvas_node"
    ]
    assert any(s == "create_node(attribute_mapper)" for s in summaries)


if __name__ == "__main__":
    test_generic_mapping_returns_choices()
    test_mapping_choice_applies_attribute_mapper()
    print("ok")
