from fastapi import APIRouter

from backend.app.api.endpoints import (
    auth,
    banco,
    bancos,
    exportacoes,
    health,
    materiais,
    orquestrador,
    prompts,
    provas,
    rag,
    sessoes,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(sessoes.router)
router.include_router(materiais.router)
router.include_router(rag.router)
router.include_router(prompts.router)
router.include_router(banco.router)
router.include_router(bancos.router)
router.include_router(provas.router)
router.include_router(exportacoes.router)
router.include_router(orquestrador.router)
