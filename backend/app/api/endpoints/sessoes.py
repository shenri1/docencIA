from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.db import get_db
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.schemas.sessao import SessaoCriar, SessaoResposta
from backend.app.services.sessao_service import (
    criar_sessao,
    listar_sessoes,
    obter_sessao,
)

router = APIRouter(prefix="/sessoes", tags=["Sessões"])


@router.post("", response_model=SessaoResposta, status_code=status.HTTP_201_CREATED)
def criar(
    dados: SessaoCriar,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> SessaoGeracao:
    return criar_sessao(db, docente, dados)


@router.get("", response_model=list[SessaoResposta])
def listar(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> list[SessaoGeracao]:
    return listar_sessoes(db, docente, limit=limit, offset=offset)


@router.get("/{sessao_id}", response_model=SessaoResposta)
def obter(
    sessao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> SessaoGeracao:
    return obter_sessao(db, docente, sessao_id)
