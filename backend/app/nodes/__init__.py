from __future__ import annotations

from typing import Dict, List, Type

from app.nodes.base import Base4GIxNode
from app.nodes.readers import FileReader, GeoJSONReader, PostGISReader
from app.nodes.transformers import (
    AttributeMapperTransformer,
    BufferTransformer,
    FilterTransformer,
    ReprojectTransformer,
)
from app.nodes.writers import FileWriter, PostGISWriter

NODE_REGISTRY: Dict[str, Type[Base4GIxNode]] = {
    cls.node_type: cls
    for cls in (
        PostGISReader,
        FileReader,
        GeoJSONReader,
        ReprojectTransformer,
        BufferTransformer,
        FilterTransformer,
        AttributeMapperTransformer,
        PostGISWriter,
        FileWriter,
    )
}


def get_node_class(node_type: str) -> Type[Base4GIxNode]:
    if not node_type or node_type not in NODE_REGISTRY:
        known = ", ".join(sorted(NODE_REGISTRY))
        raise KeyError(f"Type de nœud inconnu `{node_type}`. Types disponibles: {known}")
    return NODE_REGISTRY[node_type]


def list_catalog() -> List[dict]:
    return [cls.catalog_entry() for cls in NODE_REGISTRY.values()]
