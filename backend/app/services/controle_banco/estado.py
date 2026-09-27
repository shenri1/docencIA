"""Estado e revisão do banco — Núcleo Determinístico, nunca chama LLM.

o estado versionado é um contador (`BancoQuestoes.revisao`), não uma
cópia do banco. As questões mudam no lugar, e o histórico fica nas tabelas
append-only. "Inconsistência de estado" passa a ser comparação de inteiros.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoQuestao, EventoBanco, FaixaDificuldade, TipoQuestao
from backend.app.exceptions import (
    BancoNaoEncontradoException,
    RevisaoDesatualizadaException,
)
from backend.app.models.banco import BancoQuestoes, Questao, RelatorioImpacto
from backend.app.models.identidade import Docente
from backend.app.services.controle_banco.relatorio_impacto import calcular_impacto


def obter_banco(db: Session, docente: Docente, banco_id: int) -> BancoQuestoes:
    """Banco de outro docente responde 404, não 403 — mesma regra de
    `obter_sessao`: não revela existência."""
    banco = db.get(BancoQuestoes, banco_id)
    if banco is None or banco.sessao.docente_id != docente.id:
        raise BancoNaoEncontradoException(banco_id)
    return banco


def exigir_revisao(banco: BancoQuestoes, revisao_esperada: int) -> None:
    """Human-in-the-loop: o comando vale sobre o banco que o docente viu."""
    if revisao_esperada != banco.revisao:
        raise RevisaoDesatualizadaException(banco.revisao, revisao_esperada)


def _contagens_ativas(
    db: Session, banco: BancoQuestoes
) -> dict[TipoQuestao, dict[FaixaDificuldade, int]]:
    linhas = db.execute(
        select(Questao.tipo, Questao.faixa_dificuldade, func.count())
        .where(
            Questao.banco_id == banco.id,
            # Candidata, descartada, excluída e substituída não compõem o banco.
            Questao.estado == EstadoQuestao.ATIVA,
        )
        .group_by(Questao.tipo, Questao.faixa_dificuldade)
    ).all()
    contagens: dict[TipoQuestao, dict[FaixaDificuldade, int]] = {}
    for tipo, faixa, quantidade in linhas:
        contagens.setdefault(tipo, {})[faixa] = quantidade
    return contagens


def registrar_relatorio(
    db: Session, banco: BancoQuestoes, evento: EventoBanco
) -> RelatorioImpacto:
    """Incrementa a revisão e grava o relatório com a revisão nova.

    NÃO faz commit: roda sempre dentro da transação da mudança que o motivou,
    para que um relatório nunca sobreviva a uma exclusão desfeita.
    """
    # A sessão roda com autoflush desligado (core/db.py): sem este flush, a
    # contagem não veria as mudanças de estado que o chamador acabou de fazer.
    db.flush()
    tipos_pedidos = {
        tipo
        for tipo, n_alvo in (
            (TipoQuestao.OBJETIVA, banco.n_alvo_objetivas),
            (TipoQuestao.DISCURSIVA, banco.n_alvo_discursivas),
        )
        if n_alvo > 0
    }
    sessao = banco.sessao
    impacto = calcular_impacto(
        _contagens_ativas(db, banco),
        tipos_pedidos,
        sessao.p_f,
        sessao.p_m,
        sessao.p_d,
    )
    banco.revisao += 1
    relatorio = RelatorioImpacto(
        banco_id=banco.id,
        revisao=banco.revisao,
        evento=evento,
        n_final=impacto.n_final,
        contagem_por_faixa={
            tipo.value: {faixa.value: c for faixa, c in dados.contagem_por_faixa.items()}
            for tipo, dados in impacto.por_tipo.items()
        },
        desvio_observado={
            tipo.value: {
                faixa.value: (None if desvio is None else str(desvio))
                for faixa, desvio in dados.desvio_por_faixa.items()
            }
            for tipo, dados in impacto.por_tipo.items()
        },
        alerta_desvio=impacto.alerta_desvio,
    )
    db.add(relatorio)
    db.flush()
    return relatorio
