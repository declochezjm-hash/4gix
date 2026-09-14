"""Pipeline d'intégration : readers, transformers, writers, step architect."""

from __future__ import annotations

import json
import os
import shutil
import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from app.agent.composer import parse_parallel_branch_objectives
from app.agent.step_architect import (
    ARCHITECT_BRANCH_OFFSET_Y,
    build_step_plan,
    plan_step_architect,
)
from app.nodes.base import _as_feature_collection
from app.nodes.readers.csv_reader import CsvReader
from app.nodes.readers.shapefile_reader import ShapefileReader
from app.nodes.transformers.spatial import AttributeMapperTransformer, FilterTransformer
from app.nodes.transformers.vertex_creator import VertexCreatorNode
from app.nodes.writers.file_writer import FileWriter

_GRAPH_CSV_SOURCE = {
    "nodes": [
        {
            "id": "csv_reader-1",
            "type": "etl",
            "position": {"x": 80, "y": 200},
            "data": {
                "label": "CSV",
                "nodeType": "csv_reader",
                "outputSnapshot": {
                    "type": "FeatureCollection",
                    "crs": "EPSG:4326",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"TYPE_SOURCE": "LED"},
                            "geometry": {"type": "Point", "coordinates": [0, 0]},
                        }
                    ],
                },
            },
        },
        {
            "id": "auto_architect_agent-1",
            "type": "etl",
            "position": {"x": 380, "y": 200},
            "data": {
                "label": "Auto-Architect",
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

_INSPECT = {
    "fields": [
        {"name": "CODE_FOYER"},
        {"name": "TYPE_SOURCE"},
        {"name": "X"},
        {"name": "Y"},
    ],
    "has_geometry": True,
    "geometry_types": ["Point"],
    "crs": "EPSG:4326",
}


def _feature_count(payload: object) -> int:
    fc = _as_feature_collection(payload)
    if not fc:
        return 0
    return len(fc.get("features") or [])


def _inputs(data: object) -> dict:
    return {"input": data}


class Test4GIxPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = os.path.join(os.path.dirname(__file__), "tmp_workspace")
        os.makedirs(cls.test_dir, exist_ok=True)
        os.environ["FOURGIX_WORKSPACE_DIR"] = cls.test_dir

        cls.csv_path = os.path.join(cls.test_dir, "sample.csv")
        pd.DataFrame(
            {
                "CODE_FOYER": ["F01", "F02", "F03"],
                "TYPE_SOURCE": ["LED", "LAMPE LED", "INCANDESCENTE"],
                "X": [-1.55362, -1.55300, -1.55250],
                "Y": [47.21837, 47.21800, 47.21750],
            }
        ).to_csv(cls.csv_path, index=False)

        cls.shp_path = os.path.join(cls.test_dir, "sample.shp")
        gpd.GeoDataFrame(
            {"ID": [1, 2], "TYPE_SOURCE": ["LED", "LAMPE LED"]},
            geometry=[Point(-1.553, 47.218), Point(-1.552, 47.217)],
            crs="EPSG:4326",
        ).to_file(cls.shp_path)

    @classmethod
    def tearDownClass(cls) -> None:
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_csv_reader_and_geometry_injection(self) -> None:
        reader = CsvReader()
        raw = reader.execute({}, {"path": self.csv_path})
        self.assertEqual(_feature_count(raw["data"]), 3)

        fc = _as_feature_collection(raw["data"])
        self.assertIsNotNone(fc)
        first_geom = (fc.get("features") or [{}])[0].get("geometry")
        if first_geom:
            self.assertIn("coordinates", first_geom)
            return

        geom_creator = VertexCreatorNode()
        with_geom = geom_creator.execute(
            _inputs(raw["data"]),
            {"x_field": "X", "y_field": "Y", "target_crs": "EPSG:4326"},
        )
        fc2 = _as_feature_collection(with_geom["data"])
        self.assertIsNotNone(fc2)
        self.assertTrue(
            any(
                isinstance(f.get("geometry"), dict) and f["geometry"].get("type")
                for f in (fc2.get("features") or [])
            )
        )

    def test_02_attribute_filter_and_remapper(self) -> None:
        reader = CsvReader()
        data = reader.execute({}, {"path": self.csv_path})["data"]

        filtered = FilterTransformer().execute(
            _inputs(data),
            {
                "field": "TYPE_SOURCE",
                "operator": "contains",
                "value": "LED",
            },
        )
        self.assertEqual(_feature_count(filtered["data"]), 2)

        remapped = AttributeMapperTransformer().execute(
            _inputs(filtered["data"]),
            {"mapping": json.dumps({"CODE_FOYER": "foyer_id"})},
        )
        fc = _as_feature_collection(remapped["data"])
        self.assertIsNotNone(fc)
        props = (fc.get("features") or [{}])[0].get("properties") or {}
        self.assertIn("foyer_id", props)

    def test_03_shapefile_writer_crs_flat(self) -> None:
        reader = CsvReader()
        data = reader.execute({}, {"path": self.csv_path})["data"]
        with_geom = VertexCreatorNode().execute(
            _inputs(data),
            {"x_field": "X", "y_field": "Y", "target_crs": "EPSG:4326"},
        )

        out_shp = os.path.join(self.test_dir, "output.shp")
        FileWriter().execute(
            _inputs(with_geom["data"]),
            {
                "path": out_shp,
                "driver": "ESRI Shapefile",
                "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            },
        )
        self.assertTrue(os.path.exists(out_shp))

    def test_04_shapefile_reader_smoke(self) -> None:
        out = ShapefileReader().execute({}, {"path": self.shp_path})
        self.assertGreaterEqual(_feature_count(out["data"]), 1)

    def test_05_auto_healing_vertex_before_shapefile_export(self) -> None:
        steps, _notices = build_step_plan(
            "exporte en shapefile",
            {
                "fields": [
                    {"name": "TYPE_SOURCE"},
                    {"name": "X"},
                    {"name": "Y"},
                ],
                "crs": "EPSG:4326",
                "has_geometry": False,
                "geometry_types": [],
            },
        )
        node_types = [step.node_type for step in steps]
        self.assertIn("vertex_creator", node_types)
        self.assertIn("shapefile_writer", node_types)
        self.assertLess(
            node_types.index("vertex_creator"),
            node_types.index("shapefile_writer"),
        )

    def test_06_step_architect_parallel_dag(self) -> None:
        # Formulation alignée sur parse_parallel_branch_objectives (séparateur « et un autre filtre »).
        prompt = (
            "fait moi un filtre sur le type de source LED et genere moi un shp "
            "et un autre filtre sur le type de source Lampe LED et genere un geojson"
        )
        branches = parse_parallel_branch_objectives(
            prompt,
            ["TYPE_SOURCE"],
        )
        self.assertEqual(len(branches), 2)
        self.assertEqual(branches[0].writer_type, "shapefile_writer")
        self.assertEqual(branches[1].writer_type, "geojson_writer")

        steps, _ = build_step_plan(prompt, _INSPECT)
        self.assertEqual(len(steps), 4)
        self.assertEqual(
            [s.node_type for s in steps],
            [
                "attribute_filter",
                "shapefile_writer",
                "attribute_filter",
                "geojson_writer",
            ],
        )

        graph = dict(_GRAPH_CSV_SOURCE)
        previous: list[dict] = []
        y_branch0: float | None = None
        for index in range(4):
            result = plan_step_architect(
                global_objective=prompt,
                current_step_index=index,
                previous_steps=previous,
                current_graph=graph,
                source_node_id="csv_reader-1",
                layout_anchor_node_id="auto_architect_agent-1",
            )
            self.assertFalse(result["is_complete"])
            pos_y = result["proposed_node"]["position"]["y"]
            if index == 0:
                y_branch0 = pos_y
            elif index == 2:
                self.assertIsNotNone(y_branch0)
                self.assertGreaterEqual(
                    pos_y - y_branch0,
                    ARCHITECT_BRANCH_OFFSET_Y - 1,
                )
            previous.append(
                {
                    "index": index,
                    "node_id": result["proposed_node"]["id"],
                    "step_summary": result["step_summary"],
                    "branch_id": result.get("branch_id"),
                }
            )
            graph = {
                "nodes": [*graph["nodes"], result["proposed_node"]],
                "edges": [*graph["edges"], result["proposed_edge"]],
                "snapshots": {},
            }

        done = plan_step_architect(
            global_objective=prompt,
            current_step_index=4,
            previous_steps=previous,
            current_graph=graph,
            source_node_id="csv_reader-1",
        )
        self.assertTrue(done["is_complete"])
        self.assertEqual(done["total_steps"], 4)


if __name__ == "__main__":
    unittest.main()
