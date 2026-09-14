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
from app.nodes.transformers.vertex_creator import CoordinateSetterNode, VertexCreatorNode
from app.nodes.transformers.composer_agent import ComposerAgentNode
from app.nodes.transformers.direct_agent_processor import DirectAgentProcessorNode
from app.nodes.transformers.auto_architect_agent import AutoArchitectAgentNode

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
        VertexCreatorNode,
        CoordinateSetterNode,
        ComposerAgentNode,
        DirectAgentProcessorNode,
        AutoArchitectAgentNode,
        PostGISWriter,
        FileWriter,
        LogWriter,
    )
}


_NODE_TYPE_ALIASES: dict[str, str] = {
    "shapefile_writer": "file_writer",
    "geojson_writer": "file_writer",
    "vector_writer": "file_writer",
    "gpkg_writer": "file_writer",
    "csv_writer": "file_writer",
    "filter_transformer": "attribute_filter",
    "filter": "attribute_filter",
    "reprojector": "reproject",
    "bufferer": "buffer",
}


def _normalize_node_type_key(node_type: str) -> str:
    import re

    key = (node_type or "").strip().replace("-", "_")
    key = re.sub(r"([a-z])([A-Z])", r"\1_\2", key)
    return key.lower()


def get_node_class(node_type: str) -> Type[Base4GIxNode]:
    node_type = _normalize_node_type_key(node_type)
    if node_type in _NODE_TYPE_ALIASES:
        node_type = _NODE_TYPE_ALIASES[node_type]
    if node_type == "code_node":
        return PythonCallerNode
    if node_type == "composer_agent":
        return ComposerAgentNode
    if node_type == "direct_agent_processor":
        return DirectAgentProcessorNode
    if node_type == "auto_architect_agent":
        return AutoArchitectAgentNode
    if not node_type or node_type not in NODE_REGISTRY:
        known = ", ".join(sorted(NODE_REGISTRY))
        raise KeyError(f"Type de nœud inconnu `{node_type}`. Types disponibles: {known}")
    return NODE_REGISTRY[node_type]


def list_catalog() -> List[dict]:
    return [cls.catalog_entry() for cls in NODE_REGISTRY.values()]
