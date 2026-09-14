from fastapi import APIRouter

from app.api.v1.endpoints.agent import router as agent_router
from app.api.v1.endpoints.credentials import router as credentials_router
from app.api.v1.endpoints.direct_process import router as direct_process_router
from app.api.v1.endpoints.upload import router as upload_router

router = APIRouter(prefix="/api/v1")
router.include_router(upload_router)
router.include_router(agent_router)
router.include_router(direct_process_router)
router.include_router(credentials_router)
