"""Casos de uso de sessão de geração — Núcleo Determinístico, nunca chama LLM."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoSessao
from backend.app.exceptions import (
    IndiceNaoConfirmadoException,
    SessaoNaoEncontradaException,
)
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.schemas.sessao import SessaoCriar
from backend.app.services.validacao_parametros_service import validar_distribuicao


def criar_sessao(db: Session, docente: Docente, dados: SessaoCriar) -> SessaoGeracao:
    validar_distribuicao(dados.p_f, dados.p_m, dados.p_d)
    sessao = SessaoGeracao(
        docente_id=docente.id,
        disciplina=dados.disciplina,
        periodo=dados.periodo,
        tema_escopo=dados.tema_escopo,
        area_do_conhecimento=dados.area_do_conhecimento,
        k_alternativas=dados.k_alternativas,
        p_f=dados.p_f,
        p_m=dados.p_m,
        p_d=dados.p_d,
        estado=EstadoSessao.RASCUNHO,
    )
    db.add(sessao)
    db.commit()
    db.refresh(sessao)
    return sessao


def listar_sessoes(
    db: Session, docente: Docente, limit: int = 20, offset: int = 0
) -> list[SessaoGeracao]:
    consulta = (
        select(SessaoGeracao)
        .where(SessaoGeracao.docente_id == docente.id)
        .order_by(SessaoGeracao.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(consulta))


def obter_sessao(db: Session, docente: Docente, sessao_id: int) -> SessaoGeracao:
    """Sessão de outro docente responde 404, não 403: não revela existência."""
    sessao = db.get(SessaoGeracao, sessao_id)
    if sessao is None or sessao.docente_id != docente.id:
        raise SessaoNaoEncontradaException(sessao_id)
    return sessao


def exigir_indice_confirmado(sessao: SessaoGeracao) -> None:
    """geração bloqueada enquanto o docente não confirmar o índice.
    Consumido (Agente Gerador)."""
    if sessao.estado == EstadoSessao.RASCUNHO:
        raise IndiceNaoConfirmadoException()
