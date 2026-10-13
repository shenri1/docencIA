from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.db import get_db
from backend.app.models.identidade import Docente
from backend.app.models.orientacoes import OrientacaoDocente
from backend.app.schemas.orientacao import OrientacaoCriar, OrientacaoResposta
from backend.app.services.orientacoes.orientacao_service import (
    criar_orientacao_sessao,
    desativar,
    listar,
)
from backend.app.services.sessao_service import obter_sessao

router = APIRouter(
    prefix="/sessoes/{sessao_id}/orientacoes", tags=["Orientações do Docente"]
)


@router.get("", response_model=list[OrientacaoResposta])
def listar_orientacoes(
    sessao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> list[OrientacaoDocente]:
    return listar(db, obter_sessao(db, docente, sessao_id))


@router.post("", response_model=OrientacaoResposta, status_code=status.HTTP_201_CREATED)
def acrescentar(
    sessao_id: int,
    dados: OrientacaoCriar,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> OrientacaoDocente:
    # Permitida em qualquer estado da sessão: só afeta gerações futuras.
    sessao = obter_sessao(db, docente, sessao_id)
    return criar_orientacao_sessao(db, docente, sessao, dados.o_que_mudar)


@router.post("/{orientacao_id}/desativar", response_model=OrientacaoResposta)
def desativar_orientacao(
    sessao_id: int,
    orientacao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> OrientacaoDocente:
    sessao = obter_sessao(db, docente, sessao_id)
    return desativar(db, docente, sessao, orientacao_id)
