"""Vérifie le Direct Chat Processor (surface > 500)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

import geopandas as gpd

from app.agent.direct_processor import process_direct
from app.api.v1.endpoints.direct_process import router as direct_process_router

SURFACE_CODE = """def transform(gdf):
    gdf = gdf.copy()
    return gdf[gdf.geometry.area > 500]
"""

PROMPT = "Filtre uniquement les entités dont la surface est > 500"


def _sample_graph() -> dict:
    small = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    large = Polygon([(0, 0), (30, 0), (30, 30), (0, 30)])
    gdf = gpd.GeoDataFrame(
        {"name": ["petit", "grand"]},
        geometry=[small, large],
        crs="EPSG:3857",
    )
    fc = gdf.__geo_interface__
    fc["features"][0]["properties"] = {"name": "petit"}
    fc["features"][1]["properties"] = {"name": "grand"}
    return {
        "nodes": [
            {
                "id": "reader-1",
                "type": "etl",
                "data": {
                    "nodeType": "shapefile_reader",
                    "outputSnapshot": fc,
                },
            },
            {
                "id": "agent-1",
                "type": "etl",
                "data": {"nodeType": "composer_agent"},
            },
        ],
        "edges": [{"source": "reader-1", "target": "agent-1"}],
        "snapshots": {},
    }


def main() -> None:
    small = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    large = Polygon([(0, 0), (30, 0), (30, 30), (0, 30)])
    gdf = gpd.GeoDataFrame(
        {"name": ["petit", "grand"]},
        geometry=[small, large],
        crs="EPSG:3857",
    )
    result = process_direct(gdf, PROMPT, "test-key", llm_code=SURFACE_CODE)
    assert result["ok"] is True
    assert result["feature_count_before"] == 2
    assert result["feature_count_after"] == 1
    assert result["gdf"].iloc[0]["name"] == "grand"

    graph = _sample_graph()
    app = FastAPI()
    app.include_router(direct_process_router, prefix="/api/v1")

    with patch(
        "app.agent.direct_processor.call_llm",
        return_value=SURFACE_CODE,
    ):
        client = TestClient(app)
        response = client.post(
            "/api/v1/agent/direct-process",
            json={
                "node_id": "agent-1",
                "prompt": PROMPT,
                "sample_limit": 500,
                "current_graph": graph,
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["feature_count_after"] == 1
    assert body["parent_node_id"] == "reader-1"
    snap = body["snapshot"]
    from app.nodes.workflow_features import extract_port

    fc = extract_port(snap.get("output_snapshot"), "output")
    features = fc.get("features") or []
    assert len(features) == 1
    assert features[0]["properties"].get("name") == "grand"
    print("OK direct-process")


if __name__ == "__main__":
    main()
