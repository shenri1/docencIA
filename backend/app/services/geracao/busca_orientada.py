"""Busca da âncora mais a de cada "articular com" — Núcleo Semântico,
porque embute as consultas. Não chama o modelo de geração.

A consulta de um cruzamento combina o assunto com o texto da âncora. Só o
assunto daria os mesmos trechos para todas as questões do banco, e uma
orientação acumulada repetiria o mesmo cruzamento 25 vezes. Não há limiar de
score para concluir que "o material não cobre X": quem decide se os trechos
sustentam a relação é o Gerador, que declara insuficiência.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial
from backend.app.services.rag.retrieval_service import TrechoRecuperado, buscar

if TYPE_CHECKING:
    from backend.app.services.metricas.coletor import Coletor


def trechos_com_orientacoes(
    db: Session,
    embeddings,
    reranker,
    sessao: SessaoGeracao,
    ancora: ChunkMaterial,
    orientacoes: Sequence,
    coletor: Coletor | None = None,
) -> list[TrechoRecuperado]:
    trechos = buscar(
        db,
        embeddings,
        reranker,
        sessao,
        ancora.texto,
        k=settings.rag_top_k,
        candidatos=settings.rag_candidatos,
        coletor=coletor,
    )
    cruzamentos = [o.cruzar_com for o in orientacoes if o.cruzar_com]
    if not cruzamentos:
        return trechos
    for assunto in cruzamentos:
        # `buscar` filtra pela sessão: o cruzamento só alcança o material dela (R2).
        trechos += buscar(
            db,
            embeddings,
            reranker,
            sessao,
            f"{assunto}\n{ancora.texto}",
            k=settings.rag_top_k_cruzamento,
            candidatos=settings.rag_candidatos_cruzamento,
            coletor=coletor,
            origem=f"cruzamento:{assunto}",
        )
    # O texto entra na chave: um bloco longo vira vários chunks com a mesma
    # localização (chunking.py), e eles não são repetidos.
    vistos: set[tuple[int, str, str]] = set()
    unicos: list[TrechoRecuperado] = []
    for trecho in trechos:
        chave = (trecho.material_id, trecho.localizacao, trecho.texto)
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(trecho)
    return unicos
