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
from app.nodes.connectors import HumanApprovalNode, build_connector_classes

_NODE_CLASSES = (
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
        HumanApprovalNode,
)

NODE_REGISTRY: Dict[str, Type[Base4GIxNode]] = {
    cls.node_type: cls for cls in _NODE_CLASSES
}
NODE_REGISTRY.update(build_connector_classes())


def get_node_class(node_type: str) -> Type[Base4GIxNode]:
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
    seen: set[str] = set()
    entries: List[dict] = []
    for cls in _NODE_CLASSES:
        if cls.node_type in seen:
            continue
        seen.add(cls.node_type)
        entries.append(cls.catalog_entry())
    for node_type, cls in sorted(NODE_REGISTRY.items()):
        if node_type in seen:
            continue
        seen.add(node_type)
        entries.append(cls.catalog_entry())
    return entries
