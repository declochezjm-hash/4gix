"""Vérifie POST /api/v1/agent/step-architect (plan + étape 1)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.composer import detect_export_writer, parse_target_crs, _wants_reproject
from app.agent.step_architect import build_step_plan, plan_step_architect
from app.api.v1.endpoints.agent import router as agent_router

OBJECTIVE = (
    "Reprojeter en EPSG:2154, filtrer les parcelles dont la surface est > 1000 m², "
    "puis exporter en GeoJSON"
)

CSV_CC43_OBJECTIVE = (
    "Analyse le csv, fait une reprojection en CC43, et genere un shp"
)

GRAPH = {
    "nodes": [
        {
            "id": "shapefile_reader-1",
            "type": "etl",
            "position": {"x": 80, "y": 160},
            "data": {
                "label": "Shapefile",
                "nodeType": "shapefile_reader",
                "outputSnapshot": {
                    "type": "FeatureCollection",
                    "crs": "EPSG:4326",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"id_parcelle": 1, "surface_m2": 500},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                            },
                        }
                    ],
                },
            },
        }
    ],
    "edges": [],
    "snapshots": {},
}

GRAPH_CSV_ARCHITECT = {
    "nodes": [
        {
            "id": "csv_reader-1",
            "type": "etl",
            "position": {"x": 80, "y": 200},
            "data": {
                "label": "CSV — Pl reno",
                "nodeType": "csv_reader",
                "outputSnapshot": {
                    "type": "FeatureCollection",
                    "crs": "EPSG:4326",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"id": 1},
                            "geometry": {"type": "Point", "coordinates": [0, 0]},
                        }
                    ],
                },
            },
        },
        {
            "id": "auto_architect_agent-1",
            "type": "etl",
            "position": {"x": 380, "y": 160},
            "data": {
                "label": "Auto-Architect Agent",
                "nodeType": "auto_architect_agent",
            },
        },
    ],
    "edges": [
        {
            "id": "e-csv-architect",
            "source": "csv_reader-1",
            "target": "auto_architect_agent-1",
        }
    ],
    "snapshots": {},
}


def test_cc43_shp_intent_mapping() -> None:
    assert parse_target_crs(CSV_CC43_OBJECTIVE) == "EPSG:3943"
    assert _wants_reproject(CSV_CC43_OBJECTIVE) is True
    assert detect_export_writer(CSV_CC43_OBJECTIVE) == "shapefile_writer"
    steps = build_step_plan(CSV_CC43_OBJECTIVE, {"crs": "EPSG:4326"})
    assert [step.node_type for step in steps] == [
        "attribute_manager",
        "reprojector",
        "shapefile_writer",
    ]
    assert steps[1].config["target_crs"] == "EPSG:3943"


def test_csv_cc43_pipeline_anchors_on_auto_architect() -> None:
    result = plan_step_architect(
        global_objective=CSV_CC43_OBJECTIVE,
        current_step_index=0,
        previous_steps=[],
        current_graph=GRAPH_CSV_ARCHITECT,
        source_node_id="csv_reader-1",
        layout_anchor_node_id="auto_architect_agent-1",
    )
    assert result["ok"] is True
    assert result["is_complete"] is False
    assert result["total_steps"] == 3
    assert len(result["global_plan"]) == 3
    assert result["proposed_edge"]["source"] == "auto_architect_agent-1"
    pos0 = result["proposed_node"]["position"]
    assert pos0["x"] == 380 + 300
    assert pos0["y"] == 160

    node1_id = result["proposed_node"]["id"]
    graph_step2 = {
        "nodes": [*GRAPH_CSV_ARCHITECT["nodes"], result["proposed_node"]],
        "edges": [*GRAPH_CSV_ARCHITECT["edges"], result["proposed_edge"]],
        "snapshots": {},
    }
    step2 = plan_step_architect(
        global_objective=CSV_CC43_OBJECTIVE,
        current_step_index=1,
        previous_steps=[
            {
                "index": 0,
                "node_id": node1_id,
                "step_summary": result["step_summary"],
            }
        ],
        current_graph=graph_step2,
        source_node_id="csv_reader-1",
        layout_anchor_node_id=node1_id,
    )
    assert step2["is_complete"] is False
    assert step2["proposed_edge"]["source"] == node1_id
    pos1 = step2["proposed_node"]["position"]
    assert pos1["x"] == pos0["x"] + 300
    assert pos1["y"] == pos0["y"]

    node2_id = step2["proposed_node"]["id"]
    graph_step3 = {
        "nodes": [*graph_step2["nodes"], step2["proposed_node"]],
        "edges": [*graph_step2["edges"], step2["proposed_edge"]],
        "snapshots": {},
    }
    step3 = plan_step_architect(
        global_objective=CSV_CC43_OBJECTIVE,
        current_step_index=2,
        previous_steps=[
            {"index": 0, "node_id": node1_id, "step_summary": result["step_summary"]},
            {"index": 1, "node_id": node2_id, "step_summary": step2["step_summary"]},
        ],
        current_graph=graph_step3,
        source_node_id="csv_reader-1",
        layout_anchor_node_id=node2_id,
    )
    assert step3["is_complete"] is False
    assert step3["proposed_node"]["data"]["requestedNodeType"] == "shapefile_writer"
    assert step3["proposed_edge"]["source"] == node2_id
    pos2 = step3["proposed_node"]["position"]
    assert pos2["x"] == pos1["x"] + 300
    assert pos2["y"] == pos1["y"]

    done = plan_step_architect(
        global_objective=CSV_CC43_OBJECTIVE,
        current_step_index=3,
        previous_steps=[],
        current_graph=graph_step3,
        source_node_id="csv_reader-1",
    )
    assert done["is_complete"] is True
    assert done["total_steps"] == 3


def test_auto_detect_architect_without_explicit_anchor() -> None:
    result = plan_step_architect(
        global_objective=CSV_CC43_OBJECTIVE,
        current_step_index=0,
        previous_steps=[],
        current_graph=GRAPH_CSV_ARCHITECT,
        source_node_id="csv_reader-1",
    )
    assert result["proposed_edge"]["source"] == "auto_architect_agent-1"
    assert result["proposed_node"]["position"]["y"] == 160


def main() -> None:
    test_cc43_shp_intent_mapping()
    test_csv_cc43_pipeline_anchors_on_auto_architect()
    test_auto_detect_architect_without_explicit_anchor()

    result = plan_step_architect(
        global_objective=OBJECTIVE,
        current_step_index=0,
        previous_steps=[],
        current_graph=GRAPH,
        source_node_id="shapefile_reader-1",
    )
    assert result["ok"] is True
    plan = result["global_plan"]
    assert len(plan) >= 3
    assert "2154" in plan[0]
    assert "1000" in plan[1] or "surface" in plan[1].lower()
    assert "GeoJSON" in plan[2] or "geojson" in plan[2].lower()
    assert result["proposed_node"] is not None
    assert result["proposed_edge"] is not None
    assert result["proposed_edge"]["source"] == "shapefile_reader-1"
    assert result["step_summary"]
    assert result["next_step_hint"]
    pos0 = result["proposed_node"]["position"]
    assert pos0["x"] == 80 + 300
    assert pos0["y"] == 160

    node1_id = result["proposed_node"]["id"]
    graph_step2 = {
        "nodes": [*GRAPH["nodes"], result["proposed_node"]],
        "edges": [result["proposed_edge"]],
        "snapshots": {},
    }
    prev_steps = [
        {
            "index": 0,
            "node_id": node1_id,
            "step_summary": result["step_summary"],
        }
    ]
    step2 = plan_step_architect(
        global_objective=OBJECTIVE,
        current_step_index=1,
        previous_steps=prev_steps,
        current_graph=graph_step2,
        source_node_id="shapefile_reader-1",
    )
    assert step2["proposed_edge"]["source"] == node1_id
    assert step2["proposed_edge"]["target"] == step2["proposed_node"]["id"]
    pos1 = step2["proposed_node"]["position"]
    assert pos1["x"] == pos0["x"] + 300
    assert pos1["y"] == pos0["y"]

    app = FastAPI()
    app.include_router(agent_router, prefix="/api/v1")
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent/step-architect",
        json={
            "global_objective": OBJECTIVE,
            "current_step_index": 0,
            "previous_steps": [],
            "current_graph": GRAPH,
            "source_node_id": "shapefile_reader-1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["global_plan"] == plan
    assert body["proposed_node"]["id"]

    cc43_http = client.post(
        "/api/v1/agent/step-architect",
        json={
            "global_objective": CSV_CC43_OBJECTIVE,
            "current_step_index": 0,
            "previous_steps": [],
            "current_graph": GRAPH_CSV_ARCHITECT,
            "source_node_id": "csv_reader-1",
            "layout_anchor_node_id": "auto_architect_agent-1",
        },
    )
    assert cc43_http.status_code == 200, cc43_http.text
    cc43_body = cc43_http.json()
    assert cc43_body["total_steps"] == 3
    assert cc43_body["is_complete"] is False
    assert cc43_body["proposed_edge"]["source"] == "auto_architect_agent-1"
    print("OK step-architect", body["global_plan"])
    print("OK csv-cc43-shp", cc43_body["global_plan"])


if __name__ == "__main__":
    main()
