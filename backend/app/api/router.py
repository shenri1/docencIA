from fastapi import APIRouter

from backend.app.api.endpoints import auth, health, materiais, sessoes

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(sessoes.router)
router.include_router(materiais.router)
