"""Administração. A dependência de perfil entra no router, como em
`/prompts`: nenhuma rota nova nasce desprotegida por esquecimento."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import require_perfil
from backend.app.core.db import get_db
from backend.app.domain import PerfilDocente, TipoEventoAuditoria
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.schemas.log_auditoria import RegistroAuditoriaResposta
from backend.app.services.log_auditoria import listar_eventos

router = APIRouter(
    prefix="/admin",
    tags=["Administração"],
    dependencies=[Depends(require_perfil(PerfilDocente.ADMINISTRADOR))],
)


@router.get("/logs", response_model=list[RegistroAuditoriaResposta])
def logs(
    tipo_evento: TipoEventoAuditoria | None = Query(None),
    desde: datetime | None = Query(None, description="Inclusivo."),
    ate: datetime | None = Query(None, description="Exclusivo."),
    limite: int = Query(100, ge=1, le=500),
    deslocamento: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RegistroAuditoria]:
    return listar_eventos(db, tipo_evento, desde, ate, limite, deslocamento)
