from app.nodes.transformers.attributes import (
    AttributeManagerNode,
    CounterNode,
    DuplicateFilterNode,
    ListExploderNode,
    TesterNode,
    TestFilterNode,
)
from app.nodes.transformers.combiners import (
    FeatureMergerNode,
    NeighborFinderNode,
    SpatialRelatorNode,
)
from app.nodes.transformers.coordinates import ReprojectorNode
from app.nodes.transformers.geometry_quality import (
    GeometryFilterNode,
    GeometryValidatorNode,
    OrientorNode,
    SnapperNode,
)
from app.nodes.transformers.raster import RasterClipperNode, ZonalStatisticsNode
from app.nodes.transformers.spatial import (
    AttributeMapperTransformer,
    BufferTransformer,
    FilterTransformer,
    ReprojectTransformer,
)
from app.nodes.transformers.spatial_analysis import (
    AreaOnAreaOverlayerNode,
    BoundingBoxReplacerNode,
    BuffererNode,
    CentroidExtractorNode,
    ClipperNode,
    DensifierNode,
    DissolverNode,
    GeneralizerNode,
    LineOnLineOverlayerNode,
)
from app.nodes.transformers.python_caller import CodeNode, PythonCallerNode
from app.nodes.transformers.spatial_join import SpatialJoinNode

PALETTE_TRANSFORMERS = [
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
]

__all__ = [
    "ReprojectTransformer",
    "BufferTransformer",
    "FilterTransformer",
    "AttributeMapperTransformer",
    "SpatialJoinNode",
    "RasterClipperNode",
    "ZonalStatisticsNode",
    *[cls.__name__ for cls in PALETTE_TRANSFORMERS],
]
