"""Vérifie POST /api/v1/agent/step-architect (plan + étape 1)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.composer import (
    detect_export_writer,
    parse_parallel_branch_objectives,
    parse_target_crs,
    _wants_reproject,
)
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


PARALLEL_DAG_OBJECTIVE = (
    "fait moi un filtre sur le type de source LED et genere moi un shp "
    "et un autre filtre sur le type de source Lampe LED et genere moi un shp"
)

VALIDATION_OBJECTIVE = (
    "fait moi un filtre sur le type de source LED et fait moi un shp "
    "et un autre filtre sur le type de source Lampe LED et fait moi un shp"
)


def test_validation_phrase_filter_values() -> None:
    cols = ["TYPE_SOURCE"]
    branches = parse_parallel_branch_objectives(VALIDATION_OBJECTIVE, cols)
    assert len(branches) == 2
    assert branches[0].filter_spec["value"] == "LED"
    assert branches[1].filter_spec["value"] == "LAMPE LED"


def test_parallel_dag_filter_export_branches() -> None:
    cols = ["TYPE_SOURCE"]
    branches = parse_parallel_branch_objectives(PARALLEL_DAG_OBJECTIVE, cols)
    assert len(branches) == 2
    assert branches[0].filter_spec["value"] == "LED"
    assert branches[1].filter_spec["value"] == "LAMPE LED"
    assert branches[0].writer_type == "shapefile_writer"
    assert branches[1].writer_type == "shapefile_writer"

    steps, _notices = build_step_plan(
        PARALLEL_DAG_OBJECTIVE,
        {
            "fields": [{"name": "TYPE_SOURCE"}],
            "has_geometry": True,
            "geometry_types": ["Point"],
            "crs": "EPSG:4326",
        },
    )
    assert [s.node_type for s in steps] == [
        "attribute_filter",
        "shapefile_writer",
        "attribute_filter",
        "shapefile_writer",
    ]
    assert steps[0].attach_to_source is True and steps[0].branch_id == 0
    assert steps[1].attach_to_source is False and steps[1].branch_id == 0
    assert steps[2].attach_to_source is True and steps[2].branch_id == 1
    assert steps[3].attach_to_source is False and steps[3].branch_id == 1

    graph = dict(GRAPH_CSV_ARCHITECT)
    previous: list = []
    y_branch0: float | None = None
    y_branch1: float | None = None
    for index in range(4):
        result = plan_step_architect(
            global_objective=PARALLEL_DAG_OBJECTIVE,
            current_step_index=index,
            previous_steps=previous,
            current_graph=graph,
            source_node_id="csv_reader-1",
            layout_anchor_node_id="auto_architect_agent-1",
        )
        assert result["is_complete"] is False
        edge = result["proposed_edge"]
        node_id = result["proposed_node"]["id"]
        pos_y = result["proposed_node"]["position"]["y"]
        if index == 0:
            assert edge["source"] == "csv_reader-1"
            y_branch0 = pos_y
        elif index == 1:
            assert edge["source"] == previous[0]["node_id"]
            assert pos_y == y_branch0
        elif index == 2:
            assert edge["source"] == "csv_reader-1"
            y_branch1 = pos_y
            assert y_branch0 is not None and pos_y >= y_branch0 + 140
        elif index == 3:
            assert edge["source"] == previous[2]["node_id"]
            assert pos_y == y_branch1
        previous.append(
            {
                "index": index,
                "node_id": node_id,
                "step_summary": result["step_summary"],
                "branch_id": result["branch_id"],
            }
        )
        graph = {
            "nodes": [*graph["nodes"], result["proposed_node"]],
            "edges": [*graph["edges"], result["proposed_edge"]],
            "snapshots": {},
        }

    done = plan_step_architect(
        global_objective=PARALLEL_DAG_OBJECTIVE,
        current_step_index=4,
        previous_steps=previous,
        current_graph=graph,
        source_node_id="csv_reader-1",
    )
    assert done["is_complete"] is True
    assert done["total_steps"] == 4


def test_cc43_shp_intent_mapping() -> None:
    assert parse_target_crs(CSV_CC43_OBJECTIVE) == "EPSG:3943"
    assert _wants_reproject(CSV_CC43_OBJECTIVE) is True
    assert detect_export_writer(CSV_CC43_OBJECTIVE) == "shapefile_writer"
    steps, _notices = build_step_plan(
        CSV_CC43_OBJECTIVE,
        {
            "crs": "EPSG:4326",
            "has_geometry": True,
            "geometry_types": ["Point"],
        },
    )
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
    assert result["proposed_edge"]["source"] == "csv_reader-1"
    assert result["proposed_edge"]["sourceHandle"] == "output"
    assert result["proposed_edge"]["targetHandle"] == "input"
    pos0 = result["proposed_node"]["position"]
    assert pos0["x"] == 80 + 300
    assert pos0["y"] == 200

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
    assert result["proposed_edge"]["source"] == "csv_reader-1"
    assert result["proposed_node"]["position"]["y"] == 200


def main() -> None:
    test_validation_phrase_filter_values()
    test_parallel_dag_filter_export_branches()
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
    assert len(plan) >= 2
    assert any("2154" in step for step in plan)
    assert any("GeoJSON" in step or "geojson" in step.lower() for step in plan)
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
    assert cc43_body["proposed_edge"]["source"] == "csv_reader-1"
    print("OK step-architect", body["global_plan"])
    print("OK csv-cc43-shp", cc43_body["global_plan"])

    dual_obj = "Fait moi un filtre que les led et un filtre que les lampe led"
    dual_graph = {
        "nodes": [
            {
                "id": "csv_reader-1",
                "type": "etl",
                "position": {"x": 80, "y": 200},
                "data": {
                    "nodeType": "csv_reader",
                    "outputSnapshot": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"TYPE_SOURCE": "LED"},
                                "geometry": None,
                            }
                        ],
                    },
                },
            },
            {
                "id": "auto_architect_agent-1",
                "type": "etl",
                "position": {"x": 380, "y": 160},
                "data": {"nodeType": "auto_architect_agent"},
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
    dual0 = plan_step_architect(
        global_objective=dual_obj,
        current_step_index=0,
        previous_steps=[],
        current_graph=dual_graph,
        source_node_id="csv_reader-1",
        layout_anchor_node_id="auto_architect_agent-1",
    )
    assert dual0["total_steps"] >= 2
    assert dual0["proposed_edge"]["source"] == "csv_reader-1"
    assert dual0["proposed_node"]["data"]["params"]["value"].upper() == "LED"
    dual1 = plan_step_architect(
        global_objective=dual_obj,
        current_step_index=1,
        previous_steps=[
            {
                "index": 0,
                "node_id": dual0["proposed_node"]["id"],
                "step_summary": dual0["step_summary"],
            }
        ],
        current_graph={
            "nodes": [*dual_graph["nodes"], dual0["proposed_node"]],
            "edges": [*dual_graph["edges"], dual0["proposed_edge"]],
            "snapshots": {},
        },
        source_node_id="csv_reader-1",
        layout_anchor_node_id="auto_architect_agent-1",
    )
    assert dual1["proposed_edge"]["source"] == "csv_reader-1"
    assert "LAMPE" in str(dual1["proposed_node"]["data"]["params"]["value"]).upper()
    print("OK dual-filters", dual0["global_plan"])


if __name__ == "__main__":
    main()
