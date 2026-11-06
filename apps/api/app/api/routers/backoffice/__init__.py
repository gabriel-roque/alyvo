from fastapi import APIRouter

from app.api.routers.backoffice import catalog, knowledge, scheduling

router = APIRouter(prefix="/backoffice", tags=["backoffice"])
router.include_router(catalog.router)
router.include_router(scheduling.router)
router.include_router(knowledge.router)
