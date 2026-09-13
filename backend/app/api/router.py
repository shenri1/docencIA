from fastapi import APIRouter

from backend.app.api.endpoints import auth, health

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
