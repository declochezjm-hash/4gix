from fastapi import APIRouter

from app.api.v1.endpoints.upload import router as upload_router

router = APIRouter(prefix="/api/v1")
router.include_router(upload_router)
