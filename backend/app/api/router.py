from fastapi import APIRouter

from backend.app.api.endpoints import auth, health, materiais, prompts, rag, sessoes

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(sessoes.router)
router.include_router(materiais.router)
router.include_router(rag.router)
router.include_router(prompts.router)
