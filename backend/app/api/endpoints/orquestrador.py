"""Agente Orquestrador: marco da sessão e comando de vocabulário
fechado. As rotas de cada passo continuam existindo; estas as encadeiam."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente, get_provedor
from backend.app.core.db import get_db
from backend.app.core.storage import ArmazenamentoArquivos, get_armazenamento
from backend.app.models.identidade import Docente
from backend.app.schemas.orquestrador import (
    Comando,
    MarcoSessaoResposta,
    ResultadoComandoResposta,
)
from backend.app.services.orquestrador.marco import MarcoSessao, marco_da_sessao
from backend.app.services.orquestrador.orquestrador_service import executar_comando
from backend.app.services.provedor.provedor_service import ProvedorLLMService
from backend.app.services.rag.embeddings import Embeddings, get_embeddings
from backend.app.services.rag.rerank import Reranker, get_reranker
from backend.app.services.sessao_service import obter_sessao

router = APIRouter(prefix="/sessoes/{sessao_id}", tags=["Orquestrador"])


@router.get("/marco", response_model=MarcoSessaoResposta)
def marco(
    sessao_id: int,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
) -> MarcoSessao:
    return marco_da_sessao(db, obter_sessao(db, docente, sessao_id))


@router.post("/comando", response_model=ResultadoComandoResposta)
def comando(
    sessao_id: int,
    dados: Comando,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    armazenamento: ArmazenamentoArquivos = Depends(get_armazenamento),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
    provedor: ProvedorLLMService = Depends(get_provedor),
) -> ResultadoComandoResposta:
    # Longa no M2 e no auditar, como as rotas de origem: a retomada delas é o
    # que torna um timeout de proxy não destrutivo.
    sessao = obter_sessao(db, docente, sessao_id)
    resultado = executar_comando(
        db,
        docente,
        sessao,
        dados,
        armazenamento=armazenamento,
        embeddings=embeddings,
        reranker=reranker,
        provedor=provedor,
    )
    # Validado aqui por atributo: devolvido como dataclass, o FastAPI chamaria
    # dataclasses.asdict, que faz deepcopy dos objetos ORM do resultado.
    return ResultadoComandoResposta.model_validate(resultado, from_attributes=True)
