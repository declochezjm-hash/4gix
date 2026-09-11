from __future__ import annotations

from typing import Dict, List, Type

from app.nodes.base import Base4GIxNode
from app.nodes.readers import (
    CsvReader,
    DxfReaderNode,
    ExcelReader,
    FileReader,
    GeoJSONReader,
    GeoTiffRasterReaderNode,
    GpkgReader,
    IfcBimReaderNode,
    KmlReader,
    PostGISReader,
    RestWfsReaderNode,
    ShapefileReader,
)
from app.nodes.transformers import (
    AreaOnAreaOverlayerNode,
    AttributeManagerNode,
    AttributeMapperTransformer,
    BoundingBoxReplacerNode,
    BuffererNode,
    BufferTransformer,
    CentroidExtractorNode,
    ClipperNode,
    CounterNode,
    DensifierNode,
    DissolverNode,
    DuplicateFilterNode,
    FeatureMergerNode,
    FilterTransformer,
    GeneralizerNode,
    GeometryFilterNode,
    GeometryValidatorNode,
    LineOnLineOverlayerNode,
    ListExploderNode,
    NeighborFinderNode,
    OrientorNode,
    RasterClipperNode,
    ReprojectTransformer,
    ReprojectorNode,
    SnapperNode,
    SpatialJoinNode,
    SpatialRelatorNode,
    TesterNode,
    TestFilterNode,
    ZonalStatisticsNode,
)
from app.nodes.writers import FileWriter, LogWriter, PostGISWriter
from app.nodes.transformers.python_caller import PythonCallerNode

NODE_REGISTRY: Dict[str, Type[Base4GIxNode]] = {
    cls.node_type: cls
    for cls in (
        PostGISReader,
        FileReader,
        CsvReader,
        ExcelReader,
        GpkgReader,
        KmlReader,
        ShapefileReader,
        GeoJSONReader,
        IfcBimReaderNode,
        DxfReaderNode,
        GeoTiffRasterReaderNode,
        RestWfsReaderNode,
        ReprojectTransformer,
        BufferTransformer,
        FilterTransformer,
        AttributeMapperTransformer,
        SpatialJoinNode,
        RasterClipperNode,
        ZonalStatisticsNode,
        GeometryValidatorNode,
        GeometryFilterNode,
        SnapperNode,
        OrientorNode,
        BuffererNode,
        ClipperNode,
        DissolverNode,
        AreaOnAreaOverlayerNode,
        LineOnLineOverlayerNode,
        CentroidExtractorNode,
        BoundingBoxReplacerNode,
        DensifierNode,
        GeneralizerNode,
        FeatureMergerNode,
        SpatialRelatorNode,
        NeighborFinderNode,
        AttributeManagerNode,
        TesterNode,
        TestFilterNode,
        ListExploderNode,
        CounterNode,
        DuplicateFilterNode,
        ReprojectorNode,
        PythonCallerNode,
        PostGISWriter,
        FileWriter,
        LogWriter,
    )
}


def get_node_class(node_type: str) -> Type[Base4GIxNode]:
    if node_type == "code_node":
        return PythonCallerNode
    if not node_type or node_type not in NODE_REGISTRY:
        known = ", ".join(sorted(NODE_REGISTRY))
        raise KeyError(f"Type de nœud inconnu `{node_type}`. Types disponibles: {known}")
    return NODE_REGISTRY[node_type]


def list_catalog() -> List[dict]:
    return [cls.catalog_entry() for cls in NODE_REGISTRY.values()]
