"""Catálogo do banco — Núcleo Determinístico, nunca chama LLM.

Uma consulta sobre o que o Gerador já gravou: o "tema principal" é
`Questao.tema`, escrito.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoQuestao, FaixaDificuldade, TipoQuestao
from backend.app.models.banco import BancoQuestoes, Questao


@dataclass(frozen=True)
class ItemCatalogo:
    numero: int
    tipo: TipoQuestao
    # None só em questão que o modelo não classificou.
    tema: str | None
    faixa: FaixaDificuldade


def catalogar(db: Session, banco: BancoQuestoes) -> list[ItemCatalogo]:
    """Só ATIVA: excluída, substituída, candidata e descartada não compõem o
    banco."""
    questoes = db.scalars(
        select(Questao)
        .where(Questao.banco_id == banco.id, Questao.estado == EstadoQuestao.ATIVA)
        .order_by(Questao.numero)
    )
    return [
        ItemCatalogo(q.numero, q.tipo, q.tema, q.faixa_dificuldade) for q in questoes
    ]
