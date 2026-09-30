"""Indexação de uma sessão — orquestração de caso de uso.

O commit é por material, não por sessão. É isso que torna a retomada barata:
falha no material N deixa 1..N-1 gravados, e confirmar de novo continua em N
sem re-embutir nada.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.storage import ArmazenamentoArquivos
from backend.app.domain import EstadoSessao, OrigemTexto
from backend.app.exceptions import (
    ArtefatoDeTextoInvalidoException,
    MaterialSemTextoException,
    SessaoEstadoInvalidaException,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.services.extracao.tipos import BlocoTexto
from backend.app.services.material_service import _travar_sessao, confirmar_indice
from backend.app.services.rag.chunking import ConfigChunking, dividir_em_chunks
from backend.app.services.rag.embeddings import Embeddings


@dataclass(frozen=True)
class ResumoIndexacao:
    materiais_indexados: int
    chunks_criados: int


def _ler_blocos(
    armazenamento: ArmazenamentoArquivos, material: MaterialReferencia
) -> list[BlocoTexto]:
    """ já gravou o texto extraído: o RAG nunca refaz extração nem
    OCR, que é a operação mais cara do pipeline."""
    try:
        artefato = json.loads(armazenamento.abrir(material.chave_texto_extraido))
        return [
            BlocoTexto(
                localizacao=bloco["localizacao"],
                texto=bloco["texto"],
                origem=OrigemTexto(bloco["origem"]),
            )
            for bloco in artefato["blocos"]
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ArtefatoDeTextoInvalidoException(material.identificador_curto) from exc


def indexar_sessao(
    db: Session,
    armazenamento: ArmazenamentoArquivos,
    embeddings: Embeddings,
    sessao: SessaoGeracao,
    cfg: ConfigChunking,
) -> ResumoIndexacao:
    # Confirmar de novo é idempotente e não reindexa nada.
    if sessao.estado != EstadoSessao.RASCUNHO:
        return ResumoIndexacao(0, 0)

    pendentes = list(
        db.scalars(
            select(MaterialReferencia)
            .where(
                MaterialReferencia.sessao_id == sessao.id,
                MaterialReferencia.indexado_em.is_(None),
            )
            .order_by(MaterialReferencia.id)
        )
    )

    materiais_indexados = 0
    chunks_criados = 0
    for material in pendentes:
        blocos = _ler_blocos(armazenamento, material)
        chunks = dividir_em_chunks(blocos, cfg)
        if not chunks:
            raise MaterialSemTextoException(material.formato.value)

        vetores = embeddings.embutir_documentos([chunk.texto for chunk in chunks])
        try:
            for chunk, vetor in zip(chunks, vetores, strict=True):
                db.add(
                    ChunkMaterial(
                        material_id=material.id,
                        ordem=chunk.ordem,
                        texto=chunk.texto,
                        localizacao=chunk.localizacao,
                        vetor_embedding=vetor,
                    )
                )
            material.n_chunks = len(chunks)
            material.indexado_em = datetime.now(UTC)
            db.commit()
        except BaseException:
            db.rollback()
            raise

        materiais_indexados += 1
        chunks_criados += len(chunks)

    return ResumoIndexacao(materiais_indexados, chunks_criados)


# Cada rodada indexa embeddings de verdade (caro); duas já cobrem um upload que
# escorrega no meio. Passar disto é upload concorrente sem parar, não progresso.
MAX_RODADAS_CONFIRMACAO = 10


def indexar_e_confirmar(
    db: Session,
    armazenamento: ArmazenamentoArquivos,
    embeddings: Embeddings,
    sessao: SessaoGeracao,
    cfg: ConfigChunking,
) -> SessaoGeracao:
    """Indexa os pendentes e promove a sessão, serializando contra upload.

    O invariante da sessão em materiais_confirmados ⇒ tudo indexado —
    é garantido travando a linha da sessão antes de ler pendentes e antes de
    promover. indexar_sessao comita por material (retomada) e libera o lock
    entre materiais, então o laço re-trava e re-verifica até nenhum pendente
    sobrar; um upload que escorregar no meio é indexado na iteração seguinte.
    """
    for _ in range(MAX_RODADAS_CONFIRMACAO):
        sessao = _travar_sessao(db, sessao.id)
        if sessao.estado != EstadoSessao.RASCUNHO:
            return sessao
        indexar_sessao(db, armazenamento, embeddings, sessao, cfg)
        sessao = _travar_sessao(db, sessao.id)
        pendente = db.scalar(
            select(MaterialReferencia.id)
            .where(
                MaterialReferencia.sessao_id == sessao.id,
                MaterialReferencia.indexado_em.is_(None),
            )
            .limit(1)
        )
        if pendente is None:
            return confirmar_indice(db, sessao)
    raise SessaoEstadoInvalidaException(
        "uploads concorrentes continuam chegando e impediram a confirmação do "
        "índice; aguarde-os terminarem e confirme de novo"
    )
