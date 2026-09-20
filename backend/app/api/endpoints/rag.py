from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_docente
from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.models.identidade import Docente
from backend.app.schemas.rag import TrechoResposta
from backend.app.services.rag.embeddings import Embeddings, get_embeddings
from backend.app.services.rag.rerank import Reranker, get_reranker
from backend.app.services.rag.retrieval_service import TrechoRecuperado, buscar
from backend.app.services.sessao_service import obter_sessao

router = APIRouter(prefix="/sessoes/{sessao_id}", tags=["RAG"])


@router.get("/buscar", response_model=list[TrechoResposta])
def buscar_trechos(
    sessao_id: int,
    q: str = Query(..., min_length=3, description="Consulta em linguagem natural."),
    k: int = Query(
        default=settings.rag_top_k,
        ge=1,
        le=50,
        description="Quantos trechos devolver depois da reordenação.",
    ),
    db: Session = Depends(get_db),
    docente: Docente = Depends(get_current_docente),
    embeddings: Embeddings = Depends(get_embeddings),
    reranker: Reranker = Depends(get_reranker),
) -> list[TrechoRecuperado]:
    sessao = obter_sessao(db, docente, sessao_id)
    return buscar(
        db,
        embeddings,
        reranker,
        sessao,
        q,
        k=k,
        # O reranker só devolve `k`; candidatos nunca pode ser menor que k,
        # senão k>RAG_CANDIDATOS devolveria menos trechos que o pedido, em
        # silêncio.
        candidatos=max(k, settings.rag_candidatos),
    )
