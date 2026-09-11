from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.execution import router as execution_router
from app.api.shapefile_import import router as shapefile_import_router
from app.api.v1.router import router as api_v1_router
from app.api.fmw_workflows import router as fmw_workflows_router
from app.api.nodes_catalog import router as catalog_router
from app.api.workflows import router as workflows_router
from app.core.config import settings
from app.core.db import ensure_schema
from app.samples.bootstrap import bootstrap_samples


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    bootstrap_samples()
    yield


app = FastAPI(
    title=settings.app_name,
    description="Socle local ETL/ELT géospatial 4GIx — Recflow Engine, import .fmw, BIM, raster et WFS.",
    version="0.4.0",
    lifespan=lifespan,
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
app.include_router(workflows_router)
app.include_router(fmw_workflows_router)
app.include_router(shapefile_import_router)
app.include_router(api_v1_router)


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
        "workflows": "/api/workflows",
        "ws": "/api/ws/execute",
        "composer": "/api/v1/agent/composer",
    }
