from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.db import get_db
from backend.app.models.identidade import Docente
from backend.app.schemas.banco import BancoCriar, ResumoBancoResposta
from backend.app.services.geracao.banco_service import ResumoBanco, gerar_banco
from backend.app.services.provedor.provedor_service import criar_provedor_service
from backend.app.services.rag.embeddings import Embeddings, get_embeddings
from backend.app.services.rag.rerank import Reranker, get_reranker
from backend.app.services.sessao_service import obter_sessao

router = APIRouter(prefix="/sessoes/{sessao_id}", tags=["Banco de Questões"])


@router.post(
    "/banco", response_model=ResumoBancoResposta, status_code=status.HTTP_201_CREATED
)
def gerar(
    sessao_id: int,
    dados: BancoCriar,
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
) -> ResumoBanco:
    # Chamada longa: ~38s por questão (geração + revisão). A retomada do banco_service é o que
    # torna um timeout de proxy não destrutivo.
    sessao = obter_sessao(db, docente, sessao_id)
    return gerar_banco(
        db,
        embeddings,
        reranker,
        criar_provedor_service(db),
        sessao,
        n_alvo=dados.n_alvo,
        versao=dados.versao,
    )
