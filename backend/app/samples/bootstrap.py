"""Jeux d'exemple BIM / CAD / Raster / .fmw et workflows de démonstration."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.core.paths import workspace_subdir


def bootstrap_samples() -> dict:
    samples = workspace_subdir("samples")
    ifc_path = samples / "sample.ifc"
    dxf_path = samples / "sample.dxf"
    tif_path = samples / "sample_dem.tif"
    fme_path = samples / "fme_demo.geojson"
    errors: list[str] = []
    if not ifc_path.exists():
        try:
            _write_sample_ifc(ifc_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ifc:{exc}")
    if not dxf_path.exists():
        try:
            _write_sample_dxf(dxf_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"dxf:{exc}")
    if not tif_path.exists():
        try:
            _write_sample_dem(tif_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"dem:{exc}")
    if not fme_path.exists():
        try:
            _write_fme_demo(fme_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fme:{exc}")
    workflow_id = _seed_demo_workflow()
    fme_workflow_id = _seed_fme_workflow()
    return {
        "ifc": str(ifc_path) if ifc_path.exists() else None,
        "dxf": str(dxf_path) if dxf_path.exists() else None,
        "dem": str(tif_path) if tif_path.exists() else None,
        "fme_demo": str(fme_path) if fme_path.exists() else None,
        "workflow_id": workflow_id,
        "fme_workflow_id": fme_workflow_id,
        "errors": errors,
    }


def _write_sample_dxf(path: Path) -> None:
    import ezdxf

    doc = ezdxf.new("R2010")
    doc.layers.add("BUILDING", color=1)
    doc.layers.add("ROADS", color=3)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(2.348, 48.855), (2.356, 48.855), (2.356, 48.860), (2.348, 48.860), (2.348, 48.855)],
        dxfattribs={"layer": "BUILDING"},
    )
    msp.add_line((2.348, 48.855), (2.360, 48.850), dxfattribs={"layer": "ROADS"})
    msp.add_circle((2.3522, 48.8566), 0.0015, dxfattribs={"layer": "BUILDING"})
    doc.saveas(path)


def _write_sample_dem(path: Path) -> None:
    import rasterio
    from rasterio.transform import from_origin

    width, height = 120, 120
    west, north, res = 2.30, 48.90, 0.0015
    ys, xs = np.mgrid[0:height, 0:width]
    elevation = 35.0 + 40.0 * np.sin(xs / 12.0) + 25.0 * np.cos(ys / 15.0) + ys * 0.2
    transform = from_origin(west, north, res, res)
    wgs84 = 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433],AUTHORITY["EPSG","4326"]]'
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=wgs84,
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(elevation.astype("float32"), 1)


def _write_sample_ifc(path: Path) -> None:
    try:
        _write_sample_ifc_api(path)
        if path.exists() and path.stat().st_size > 200:
            return
    except Exception:
        pass
    path.write_text(_MINIMAL_IFC, encoding="utf-8")


def _write_sample_ifc_api(path: Path) -> None:
    import ifcopenshell
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="4GIx Demo BIM")
    ifcopenshell.api.run("unit.assign_unit", model)
    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=context,
    )
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site Paris")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Immeuble 4GIx")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="RDC")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])
    try:
        site.RefLatitude = (48, 51, 24)
        site.RefLongitude = (2, 21, 8)
        site.RefElevation = 35.0
    except Exception:
        pass
    wall = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name="Mur Nord")
    slab = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name="Dalle RDC")
    window = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWindow", name="Fenêtre 01")
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[wall, slab, window])
    try:
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=wall,
            matrix=((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)),
            is_si=True,
        )
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=window,
            matrix=((1, 0, 0, 4), (0, 1, 0, 0.4), (0, 0, 1, 1.2), (0, 0, 0, 1)),
            is_si=True,
        )
    except Exception:
        pass
    try:
        ifcopenshell.api.run(
            "geometry.add_wall_representation",
            model,
            context=body,
            length=8.0,
            height=3.0,
            thickness=0.3,
        )
    except Exception:
        pass
    model.write(str(path))


def _write_fme_demo(path: Path) -> None:
    import json

    from app.nodes.readers.geojson_reader import SAMPLE_WORKSPACE_DEMO

    path.write_text(json.dumps(SAMPLE_WORKSPACE_DEMO, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_demo_workflow() -> str | None:
    try:
        from app.core import persistence
    except Exception:
        return None
    try:
        existing = persistence.list_workflows()
        for item in existing:
            if item.get("name") == "IFC → Lambert-93 → PostGIS":
                return item.get("id")
        saved = persistence.upsert_workflow(
            name="IFC → Lambert-93 → PostGIS",
            definition=_demo_definition(),
        )
        return saved.get("id")
    except Exception:
        return None


def _demo_definition() -> dict:
    return {
        "nodes": [
            {
                "id": "ifc_bim_reader-1",
                "type": "etl",
                "position": {"x": 80, "y": 120},
                "data": {
                    "label": "IFC BIM Reader",
                    "nodeType": "ifc_bim_reader",
                    "category": "Reader",
                    "isSpatial": True,
                    "params": {
                        "path": "/workspace/samples/sample.ifc",
                        "ifc_class": "IfcBuildingElement",
                        "representation": "centroid",
                        "limit": 400,
                    },
                    "status": "idle",
                    "inputHandles": ["input"],
                },
            },
            {
                "id": "reproject-1",
                "type": "etl",
                "position": {"x": 360, "y": 120},
                "data": {
                    "label": "Reprojection",
                    "nodeType": "reproject",
                    "category": "Transformer",
                    "isSpatial": True,
                    "params": {"source_crs": "EPSG:4326", "target_crs": "EPSG:2154"},
                    "status": "idle",
                    "inputHandles": ["input"],
                },
            },
            {
                "id": "postgis_writer-1",
                "type": "etl",
                "position": {"x": 640, "y": 120},
                "data": {
                    "label": "PostGIS Writer",
                    "nodeType": "postgis_writer",
                    "category": "Writer",
                    "isSpatial": True,
                    "params": {
                        "schema_name": "gix_output",
                        "table": "bim_elements",
                        "geom_column": "geom",
                        "if_exists": "replace",
                    },
                    "status": "idle",
                    "inputHandles": ["input"],
                },
            },
        ],
        "edges": [
            {
                "id": "e-ifc-reproject",
                "source": "ifc_bim_reader-1",
                "target": "reproject-1",
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            },
            {
                "id": "e-reproject-pg",
                "source": "reproject-1",
                "target": "postgis_writer-1",
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            },
        ],
    }


def _seed_fme_workflow() -> str | None:
    try:
        from app.core import persistence
    except Exception:
        return None
    try:
        existing = persistence.list_workflows()
        for item in existing:
            if item.get("name") in (
                "Démo : Validator → Tester → Dissolver → PostGIS",
                "FME : Validator → Tester → Dissolver → PostGIS",
            ):
                return item.get("id")
        saved = persistence.upsert_workflow(
            name="Démo : Validator → Tester → Dissolver → PostGIS",
            definition=_fme_demo_definition(),
        )
        return saved.get("id")
    except Exception:
        return None


def _node(
    node_id: str,
    node_type: str,
    label: str,
    category: str,
    x: int,
    y: int,
    params: dict,
    *,
    spatial: bool = True,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> dict:
    return {
        "id": node_id,
        "type": "etl",
        "position": {"x": x, "y": y},
        "data": {
            "label": label,
            "nodeType": node_type,
            "category": category,
            "isSpatial": spatial,
            "params": params,
            "status": "idle",
            "inputHandles": inputs or ["input"],
            "outputHandles": outputs or ["output"],
        },
    }


def _fme_demo_definition() -> dict:
    return {
        "nodes": [
            _node(
                "geojson_reader-1",
                "geojson_reader",
                "GeoJSON Reader",
                "Reader",
                40,
                160,
                {"sample_set": "workspace_demo", "use_sample": True, "geojson": ""},
            ),
            _node(
                "geometry_validator-1",
                "geometry_validator",
                "GeometryValidator",
                "Transformer",
                300,
                160,
                {"repair": True, "allow_empty": False},
                outputs=["output", "rejected"],
            ),
            _node(
                "log_writer-1",
                "log_writer",
                "Log Writer",
                "Writer",
                560,
                320,
                {"filename": "rejected.json", "label": "REJECTED"},
                spatial=False,
            ),
            _node(
                "tester-1",
                "tester",
                "Tester",
                "Transformer",
                560,
                80,
                {
                    "logic": "AND",
                    "clauses": '[{"attr":"category","op":"eq","value":"urban"}]',
                },
                spatial=False,
                outputs=["passed", "failed"],
            ),
            _node(
                "attribute_manager-1",
                "attribute_manager",
                "AttributeManager",
                "Transformer",
                820,
                80,
                {
                    "operations": '[{"op":"rename","from":"name","to":"nom"},{"op":"create","name":"source","expr":"\'fme_demo\'"}]',
                },
                spatial=False,
            ),
            _node(
                "dissolver-1",
                "dissolver",
                "Dissolver",
                "Transformer",
                1080,
                80,
                {"group_by": "group"},
            ),
            _node(
                "postgis_writer-1",
                "postgis_writer",
                "PostGIS Writer",
                "Writer",
                1340,
                80,
                {
                    "schema_name": "gix_output",
                    "table": "fme_dissolved",
                    "geom_column": "geom",
                    "if_exists": "replace",
                },
            ),
        ],
        "edges": [
            {
                "id": "e-reader-validator",
                "source": "geojson_reader-1",
                "target": "geometry_validator-1",
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            },
            {
                "id": "e-validator-tester",
                "source": "geometry_validator-1",
                "target": "tester-1",
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            },
            {
                "id": "e-validator-log",
                "source": "geometry_validator-1",
                "target": "log_writer-1",
                "sourceHandle": "rejected",
                "targetHandle": "input",
                "animated": True,
            },
            {
                "id": "e-tester-am",
                "source": "tester-1",
                "target": "attribute_manager-1",
                "sourceHandle": "passed",
                "targetHandle": "input",
                "animated": True,
            },
            {
                "id": "e-am-dissolve",
                "source": "attribute_manager-1",
                "target": "dissolver-1",
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            },
            {
                "id": "e-dissolve-pg",
                "source": "dissolver-1",
                "target": "postgis_writer-1",
                "sourceHandle": "output",
                "targetHandle": "input",
                "animated": True,
            },
        ],
    }


_MINIMAL_IFC = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('sample.ifc','2026-09-10T00:00:00',('4GIx'),('GisForge'),'ifcopenshell','4GIx','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPERSON($,$,'4GIx',$,$,$,$,$);
#2=IFCORGANIZATION($,'GisForge',$,$,$);
#3=IFCPERSONANDORGANIZATION(#1,#2,$);
#4=IFCAPPLICATION(#2,'0.3','4GIx','4GIx');
#5=IFCOWNERHISTORY(#3,#4,$,.ADDED.,$,$,$,0);
#6=IFCCARTESIANPOINT((0.,0.,0.));
#7=IFCDIRECTION((0.,0.,1.));
#8=IFCDIRECTION((1.,0.,0.));
#9=IFCAXIS2PLACEMENT3D(#6,#7,#8);
#10=IFCLOCALPLACEMENT($,#9);
#11=IFCGEOMETRICREPRESENTATIONCONTEXT('Model','Model',3,1.E-05,#9,$);
#12=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);
#13=IFCUNITASSIGNMENT((#12));
#14=IFCPROJECT('0YvctdU8X9SgsH9BcE$1wA',#5,'4GIx Demo BIM',$,$,$,$,(#11),#13);
#15=IFCSITE('1YvctdU8X9SgsH9BcE$1wB',#5,'Site Paris',$,$,#10,$,$,.ELEMENT.,(48,51,24),(2,21,8),35.,$,$);
#16=IFCBUILDING('2YvctdU8X9SgsH9BcE$1wC',#5,'Immeuble 4GIx',$,$,#10,$,$,.ELEMENT.,$,$,$);
#17=IFCBUILDINGSTOREY('3YvctdU8X9SgsH9BcE$1wD',#5,'RDC',$,$,#10,$,$,.ELEMENT.,0.);
#18=IFCRELAGGREGATES('4YvctdU8X9SgsH9BcE$1wE',#5,$,$,#14,(#15));
#19=IFCRELAGGREGATES('5YvctdU8X9SgsH9BcE$1wF',#5,$,$,#15,(#16));
#20=IFCRELAGGREGATES('6YvctdU8X9SgsH9BcE$1wG',#5,$,$,#16,(#17));
#21=IFCCARTESIANPOINT((0.,0.,0.));
#22=IFCAXIS2PLACEMENT3D(#21,#7,#8);
#23=IFCLOCALPLACEMENT(#10,#22);
#24=IFCWALL('7YvctdU8X9SgsH9BcE$1wH',#5,'Mur Nord',$,$,#23,$,$,$);
#25=IFCCARTESIANPOINT((4.,0.4,1.2));
#26=IFCAXIS2PLACEMENT3D(#25,#7,#8);
#27=IFCLOCALPLACEMENT(#10,#26);
#28=IFCWINDOW('8YvctdU8X9SgsH9BcE$1wI',#5,'Fenetre 01',$,$,#27,$,$,$,1.4,1.2);
#29=IFCCARTESIANPOINT((0.,0.,0.));
#30=IFCAXIS2PLACEMENT3D(#29,#7,#8);
#31=IFCLOCALPLACEMENT(#10,#30);
#32=IFCSLAB('9YvctdU8X9SgsH9BcE$1wJ',#5,'Dalle RDC',$,$,#31,$,$,.FLOOR.);
#33=IFCRELCONTAINEDINSPATIALSTRUCTURE('AYvctdU8X9SgsH9BcE$1wK',#5,$,$,(#24,#28,#32),#17);
ENDSEC;
END-ISO-10303-21;
"""
