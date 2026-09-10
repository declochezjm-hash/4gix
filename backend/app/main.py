from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.execution import router as execution_router
from app.api.nodes_catalog import router as catalog_router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description="Socle local ETL/ELT géospatial 4GIx — Recflow Engine + catalogue de nœuds.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(execution_router)
app.include_router(catalog_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "4gix",
        "env": settings.env,
        "postgis": {
            "host": settings.postgis_host,
            "db": settings.postgis_db,
        },
    }


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "catalog": "/api/nodes",
        "execute": "/api/execute",
    }
