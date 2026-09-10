from fastapi import APIRouter

from app.nodes import NODE_REGISTRY, list_catalog

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/nodes")
def get_nodes_catalog() -> dict:
    catalog = list_catalog()
    grouped: dict[str, list] = {"Reader": [], "Transformer": [], "Writer": []}
    for entry in catalog:
        grouped.setdefault(entry["category"], []).append(entry)
    return {
        "count": len(catalog),
        "nodes": catalog,
        "by_category": grouped,
    }


@router.get("/nodes/{node_type}")
def get_node_schema(node_type: str) -> dict:
    cls = NODE_REGISTRY.get(node_type)
    if cls is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Nœud inconnu: {node_type}")
    return cls.catalog_entry()
