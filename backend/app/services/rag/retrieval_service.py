"""Busca sobre os chunks de uma sessão — Núcleo Semântico (embute a consulta).

Duas etapas: o pgvector recupera candidatos por similaridade de cosseno, e o
reranker cross-encoder reordena. Recuperação vetorial é rápida e aproximada;
rerank é lento e preciso. Usar os dois dá precisão sem varrer a base inteira
com o modelo caro.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.exceptions import SessaoNaoIndexadaException
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.services.rag.embeddings import Embeddings
from backend.app.services.rag.rerank import Reranker
from backend.app.services.sessao_service import exigir_indice_confirmado


@dataclass(frozen=True)
class TrechoRecuperado:
    material_id: int
    identificador_curto: str
    localizacao: str
    texto: str
    score: float
    score_vetorial: float


def buscar(
    db: Session,
    embeddings: Embeddings,
    reranker: Reranker,
    sessao: SessaoGeracao,
    consulta: str,
    k: int,
    candidatos: int,
) -> list[TrechoRecuperado]:
    exigir_indice_confirmado(sessao)

    # Checa se há algum chunk antes de pagar a chamada de embedding: sessão
    # confirmada sem nada indexado (pré-RAG) não deve gastar uma ida ao modelo.
    tem_chunk = db.scalar(
        select(ChunkMaterial.id)
        .join(MaterialReferencia, ChunkMaterial.material_id == MaterialReferencia.id)
        .where(MaterialReferencia.sessao_id == sessao.id)
        .limit(1)
    )
    if tem_chunk is None:
        raise SessaoNaoIndexadaException()

    vetor = embeddings.embutir_consulta(consulta)

    distancia = ChunkMaterial.vetor_embedding.cosine_distance(vetor).label("distancia")
    linhas = db.execute(
        select(ChunkMaterial, MaterialReferencia.identificador_curto, distancia)
        .join(MaterialReferencia, ChunkMaterial.material_id == MaterialReferencia.id)
        # Esta cláusula é a R2: nenhum chunk de outra sessão é alcançável, e o
        # reranker só vê o que ela deixou passar.
        .where(MaterialReferencia.sessao_id == sessao.id)
        .order_by(distancia)
        .limit(candidatos)
    ).all()

    if not linhas:
        raise SessaoNaoIndexadaException()

    ordenados = reranker.reordenar(
        consulta, [linha[0].texto for linha in linhas], top_n=k
    )
    return [
        TrechoRecuperado(
            material_id=linhas[indice][0].material_id,
            identificador_curto=linhas[indice][1],
            localizacao=linhas[indice][0].localizacao,
            texto=linhas[indice][0].texto,
            score=score,
            score_vetorial=1.0 - float(linhas[indice][2]),
        )
        for indice, score in ordenados
    ]
