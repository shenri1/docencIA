"""Busca sobre os chunks de uma sessão — Núcleo Semântico (embute a consulta).

Duas etapas: o pgvector recupera candidatos por similaridade de cosseno, e o
reranker cross-encoder reordena. Recuperação vetorial é rápida e aproximada;
rerank é lento e preciso. Usar os dois dá precisão sem varrer a base inteira
com o modelo caro.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.exceptions import SessaoNaoIndexadaException
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.services.rag.embeddings import Embeddings
from backend.app.services.rag.rerank import Reranker
from backend.app.services.sessao_service import exigir_indice_confirmado

if TYPE_CHECKING:
    from backend.app.services.metricas.coletor import Coletor


@dataclass(frozen=True)
class TrechoRecuperado:
    chunk_id: int
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
    coletor: Coletor | None = None,
    origem: str = "ancora",
) -> list[TrechoRecuperado]:
    """Com `coletor`, registra todos os candidatos com os scores. O
    reranker já pontuava todos e descartava; aqui só se guarda o que ele
    devolve, e os mesmos `k` primeiros seguem para o prompt."""
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

    with _medir(coletor, "busca_vetorial"):
        vetor = embeddings.embutir_consulta(consulta)

        distancia = ChunkMaterial.vetor_embedding.cosine_distance(vetor).label(
            "distancia"
        )
        linhas = db.execute(
            select(ChunkMaterial, MaterialReferencia.identificador_curto, distancia)
            .join(
                MaterialReferencia, ChunkMaterial.material_id == MaterialReferencia.id
            )
            # Esta cláusula é a R2: nenhum chunk de outra sessão é alcançável, e o
            # reranker só vê o que ela deixou passar.
            .where(MaterialReferencia.sessao_id == sessao.id)
            .order_by(distancia)
            .limit(candidatos)
        ).all()

    if not linhas:
        raise SessaoNaoIndexadaException()

    with _medir(coletor, "rerank"):
        ordenados = reranker.reordenar(
            consulta, [linha[0].texto for linha in linhas], top_n=len(linhas)
        )
    if coletor is not None:
        coletor.anotar_busca(origem, consulta, _candidatos(linhas, ordenados))
    return [
        TrechoRecuperado(
            chunk_id=linhas[indice][0].id,
            material_id=linhas[indice][0].material_id,
            identificador_curto=linhas[indice][1],
            localizacao=linhas[indice][0].localizacao,
            texto=linhas[indice][0].texto,
            score=score,
            score_vetorial=1.0 - float(linhas[indice][2]),
        )
        for indice, score in ordenados[:k]
    ]


def _medir(coletor: Coletor | None, etapa: str):
    return coletor.medir(etapa) if coletor is not None else nullcontext()


def _candidatos(linhas, ordenados: list[tuple[int, float]]) -> list[dict]:
    """Na ordem do pgvector; `enviado` é preenchido por `Coletor.fechar`."""
    posicao = {indice: (pos, score) for pos, (indice, score) in enumerate(ordenados)}
    return [
        {
            "chunk_id": chunk.id,
            "material": identificador,
            "localizacao": chunk.localizacao,
            "score_vetorial": round(1.0 - float(dist), 4),
            "score_rerank": posicao[i][1],
            "posicao_rerank": posicao[i][0],
            "enviado": False,
        }
        for i, (chunk, identificador, dist) in enumerate(linhas)
    ]
