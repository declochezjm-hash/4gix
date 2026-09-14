from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.composer import (
    detect_export_writer,
    extract_tool_sequence,
    parse_attribute_filter,
    plan_composer,
)
from app.api.v1.endpoints.agent import router as agent_router

PROMPT = (
    "Prends le CSV en entrée, filtre la colonne 'POPULATION' > 5000 "
    "et exporte en GeoPackage"
)


def main() -> None:
    print("filter", parse_attribute_filter(PROMPT))
    print("writer", detect_export_writer(PROMPT))
    graph = {
        "nodes": [
            {
                "id": "csv_reader-1",
                "type": "etl",
                "position": {"x": 80, "y": 160},
                "data": {
                    "label": "CSV",
                    "nodeType": "csv_reader",
                    "params": {"path": "/workspace/communes.csv"},
                    "outputSnapshot": {
                        "type": "FeatureCollection",
                        "crs": "EPSG:4326",
                        "features": [
                            {
                                "type": "Feature",
                                "properties": {"POPULATION": 12000, "NOM": "A"},
                                "geometry": {"type": "Point", "coordinates": [0, 0]},
                            }
                        ],
                    },
                },
            }
        ],
        "edges": [],
    }
    events = plan_composer(
        PROMPT,
        graph,
        selected_node_id="csv_reader-1",
        context_mentions=["@Input", "@Schema"],
    )
    seq = extract_tool_sequence(events)
    print("SEQUENCE", seq)
    assert seq[0] == "create_node(attribute_filter)"
    assert seq[1].startswith("connect(")
    assert seq[2] == "create_node(gpkg_writer)"
    assert seq[3].startswith("connect(")

    app = FastAPI()
    app.include_router(agent_router, prefix="/api/v1")
    client = TestClient(app)
    response = client.post(
        "/api/v1/agent/composer",
        json={
            "prompt": PROMPT,
            "current_graph": graph,
            "selected_node_id": "csv_reader-1",
            "context_mentions": ["@Schema", "@Input"],
        },
    )
    print("HTTP", response.status_code, response.headers.get("content-type"))
    body = response.text
    print(body[:1500])
    assert "create_node(attribute_filter)" in body
    assert "create_node(gpkg_writer)" in body
    assert "event: tool_call" in body
    assert "event: thought" in body
    print("OK")


if __name__ == "__main__":
    main()
