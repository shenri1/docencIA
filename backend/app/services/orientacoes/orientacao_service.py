"""Orientações do docente — Núcleo Determinístico, nunca chama LLM.

Grava, conta e encaminha. Nunca lê o texto de uma orientação: o teto é uma
contagem, e nenhuma regra depende do que o docente escreveu.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoOrientacao, OrigemOrientacao, TipoEventoAuditoria
from backend.app.exceptions import (
    EstadoOrientacaoInvalidoException,
    LimiteOrientacoesException,
    OrientacaoNaoEncontradaException,
    SessaoNaoEncontradaException,
)
from backend.app.models.banco import BancoQuestoes
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.models.orientacoes import OrientacaoDocente
from backend.app.services.log_auditoria import registrar_evento

# Confirmados em 2026-10-09; a medição diz se
# mudam. Cada "articular com" custa um embedding e até 10 chamadas de rerank no
# qwen3:1.7b, que disputa a placa com o 9b, em toda questão.
TETO_ATIVAS = 5
TETO_CRUZAMENTOS = 2


def _travar_sessao(db: Session, sessao_id: int) -> SessaoGeracao:
    """FOR UPDATE antes de contar: duas abas acrescentando a 5ª orientação ao
    mesmo tempo contariam 4 cada uma e passariam do teto."""
    sessao = db.get(
        SessaoGeracao, sessao_id, with_for_update=True, populate_existing=True
    )
    if sessao is None:
        raise SessaoNaoEncontradaException(sessao_id)
    return sessao


def _ativas(db: Session, sessao_id: int) -> list[OrientacaoDocente]:
    return list(
        db.scalars(
            select(OrientacaoDocente)
            .where(
                OrientacaoDocente.sessao_id == sessao_id,
                OrientacaoDocente.estado == EstadoOrientacao.ATIVA,
            )
            .order_by(OrientacaoDocente.id)
        )
    )


def _exigir_teto(db: Session, sessao: SessaoGeracao, com_cruzamento: bool) -> None:
    ativas = _ativas(db, sessao.id)
    cruzadas = sum(1 for o in ativas if o.cruzar_com is not None)
    if len(ativas) >= TETO_ATIVAS or (com_cruzamento and cruzadas >= TETO_CRUZAMENTOS):
        raise LimiteOrientacoesException(
            len(ativas), cruzadas, TETO_ATIVAS, TETO_CRUZAMENTOS
        )


def _gravar(db: Session, docente: Docente, orientacao: OrientacaoDocente) -> OrientacaoDocente:
    db.add(orientacao)
    db.flush()  # id para o evento
    registrar_evento(
        db,
        TipoEventoAuditoria.ORIENTACAO_CRIADA,
        f"orientacoes_docente:{orientacao.id}",
        docente.id,
        {
            "orientacao_id": orientacao.id,
            "origem": orientacao.origem.value,
            "estado": orientacao.estado.value,
            "com_cruzamento": orientacao.cruzar_com is not None,
        },
    )
    return orientacao


def registrar_iniciais(
    db: Session, docente: Docente, sessao: SessaoGeracao, textos: list[str]
) -> None:
    """As orientações do formulário da nova sessão. Sem commit: entram na
    transação da criação. Sessão nova não tem nenhuma ativa, então basta contar
    o que chegou."""
    if len(textos) > TETO_ATIVAS:
        raise LimiteOrientacoesException(len(textos), 0, TETO_ATIVAS, TETO_CRUZAMENTOS)
    for texto in textos:
        _gravar(
            db,
            docente,
            OrientacaoDocente(
                sessao_id=sessao.id,
                origem=OrigemOrientacao.SESSAO,
                estado=EstadoOrientacao.ATIVA,
                o_que_mudar=texto,
            ),
        )


def criar_orientacao_sessao(
    db: Session, docente: Docente, sessao: SessaoGeracao, o_que_mudar: str
) -> OrientacaoDocente:
    """Permitida em qualquer estado da sessão: só afeta gerações futuras."""
    sessao = _travar_sessao(db, sessao.id)
    _exigir_teto(db, sessao, com_cruzamento=False)
    orientacao = _gravar(
        db,
        docente,
        OrientacaoDocente(
            sessao_id=sessao.id,
            origem=OrigemOrientacao.SESSAO,
            estado=EstadoOrientacao.ATIVA,
            o_que_mudar=o_que_mudar,
        ),
    )
    db.commit()
    return orientacao


def criar_orientacao_questao(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    numero: int,
    cruzar_com: str | None,
    o_que_mudar: str | None,
    acumular: bool,
) -> OrientacaoDocente:
    """A orientação de uma variação guiada. Commitada antes da chamada ao
    modelo: a candidata aponta para ela, e uma insuficiência deixa o registro
    de que o docente pediu e o material não sustentou."""
    sessao = banco.sessao
    if acumular:
        sessao = _travar_sessao(db, sessao.id)
        _exigir_teto(db, sessao, com_cruzamento=cruzar_com is not None)
    orientacao = _gravar(
        db,
        docente,
        OrientacaoDocente(
            sessao_id=sessao.id,
            origem=OrigemOrientacao.QUESTAO,
            estado=EstadoOrientacao.ATIVA if acumular else EstadoOrientacao.PONTUAL,
            o_que_mudar=o_que_mudar,
            cruzar_com=cruzar_com,
            banco_id=banco.id,
            numero_origem=numero,
        ),
    )
    db.commit()
    return orientacao


def desativar(
    db: Session, docente: Docente, sessao: SessaoGeracao, orientacao_id: int
) -> OrientacaoDocente:
    """ATIVA → INATIVA, o único UPDATE da tabela. Idempotente sobre INATIVA."""
    orientacao = db.get(OrientacaoDocente, orientacao_id)
    if orientacao is None or orientacao.sessao_id != sessao.id:
        raise OrientacaoNaoEncontradaException(orientacao_id)
    if orientacao.estado is EstadoOrientacao.PONTUAL:
        raise EstadoOrientacaoInvalidoException(orientacao_id)
    if orientacao.estado is EstadoOrientacao.ATIVA:
        orientacao.estado = EstadoOrientacao.INATIVA
        registrar_evento(
            db,
            TipoEventoAuditoria.ORIENTACAO_DESATIVADA,
            f"orientacoes_docente:{orientacao.id}",
            docente.id,
            {"orientacao_id": orientacao.id},
        )
        db.commit()
    return orientacao


def listar(db: Session, sessao: SessaoGeracao) -> list[OrientacaoDocente]:
    """Todas, em qualquer estado: nenhuma orientação é apagada."""
    return list(
        db.scalars(
            select(OrientacaoDocente)
            .where(OrientacaoDocente.sessao_id == sessao.id)
            .order_by(OrientacaoDocente.id)
        )
    )


def vigentes(db: Session, sessao: SessaoGeracao) -> list[OrientacaoDocente]:
    """As que entram em toda geração da sessão: só ATIVA, em ordem de criação."""
    return _ativas(db, sessao.id)
