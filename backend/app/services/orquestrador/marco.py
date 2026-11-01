"""Marco da sessão e de cada banco — Núcleo Determinístico, sem escrita.

O marco é derivado do estado gravado a cada pedido. Gravá-lo criaria uma
segunda fonte de verdade que pode divergir do banco e das provas. `EstadoSessao`
só separa M1 do resto: ele é da sessão, e a sessão pode ter vários bancos.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.domain import (
    ComandoOrquestrador,
    EstadoBanco,
    EstadoQuestao,
    EstadoSessao,
    Marco,
    TipoQuestao,
)
from backend.app.models.banco import BancoQuestoes, Questao
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import MaterialReferencia
from backend.app.models.provas import ExportacaoDocx, Prova
from backend.app.services.controle_banco.estado import impacto_atual
from backend.app.services.critico.auditor_service import montar_resumo

_P, _E, _A = (
    ComandoOrquestrador.PROSSEGUIR,
    ComandoOrquestrador.EXCLUIR,
    ComandoOrquestrador.AUDITAR,
)

COMANDOS: dict[Marco, tuple[ComandoOrquestrador, ...]] = {
    Marco.M1_MATERIAIS: (_P,),
    Marco.M2_BANCO: (_P,),
    Marco.M3_EXCLUSOES: (_P, _E, _A),
    # Auditar vale com o banco aberto ou congelado.
    Marco.M6_PROVAS: (_P, _A),
    Marco.M10_DOCX: (_P, _A),
    Marco.CONCLUIDO: (_A,),
    Marco.BLOQUEADO: (_A,),
}

# Exatamente estes: falta ou sobra é recusada (CAMPOS_DO_MARCO).
CAMPOS_PROSSEGUIR: dict[Marco, tuple[str, ...]] = {
    Marco.M1_MATERIAIS: (),
    Marco.M2_BANCO: ("versao", "n_objetivas", "n_discursivas"),
    Marco.M3_EXCLUSOES: ("versao", "revisao_esperada"),
    Marco.M6_PROVAS: ("versao", "revisao_esperada", "n_objetivas", "n_discursivas"),
    Marco.M10_DOCX: ("versao", "revisao_esperada"),
    Marco.CONCLUIDO: (),
    Marco.BLOQUEADO: (),
}


@dataclass(frozen=True)
class MarcoBanco:
    versao: str
    banco_id: int
    revisao: int
    marco: Marco
    motivo: str | None
    n_alvo: int
    n_atual: int
    lacunas: int
    alerta_desvio: bool
    objetivas_ativas: int
    objetivas_auditadas: int
    comandos: list[ComandoOrquestrador]
    campos_prosseguir: list[str]


@dataclass(frozen=True)
class MarcoSessao:
    sessao_id: int
    marco: Marco
    n_materiais: int
    comandos: list[ComandoOrquestrador]
    campos_prosseguir: list[str]
    bancos: list[MarcoBanco]


def banco_da_versao(
    db: Session, sessao: SessaoGeracao, versao: str
) -> BancoQuestoes | None:
    return db.scalar(
        select(BancoQuestoes).where(
            BancoQuestoes.sessao_id == sessao.id, BancoQuestoes.versao == versao
        )
    )


def classificar_banco(db: Session, banco: BancoQuestoes) -> tuple[Marco, str | None]:
    """Marco e, só em BLOQUEADO, o motivo. A ordem dos testes é a dos marcos."""
    if banco.estado is EstadoBanco.ABERTO:
        # Mesmo com provas de outro banco na sessão: excluir, auditar e
        # congelar continuam valendo; só montar é que não.
        return Marco.M3_EXCLUSOES, None
    provas = list(db.scalars(select(Prova).where(Prova.sessao_id == banco.sessao_id)))
    if not provas:
        return Marco.M6_PROVAS, None
    de_outro = [p for p in provas if p.banco_id != banco.id]
    if de_outro:
        return Marco.BLOQUEADO, (
            f"A sessão já tem as provas do banco {de_outro[0].banco.versao}: uma "
            "sessão tem um par A/B só, e remontar não é suportado."
        )
    desatualizadas = [p for p in provas if p.revisao_banco != banco.revisao]
    if desatualizadas:
        return Marco.BLOQUEADO, (
            f"As provas são da revisão {desatualizadas[0].revisao_banco} e o banco "
            f"está na revisão {banco.revisao}. Remontar não é suportado; o DOCX "
            "já exportado continua disponível."
        )
    exportado = db.scalar(
        select(ExportacaoDocx.id)
        .where(
            ExportacaoDocx.banco_id == banco.id,
            ExportacaoDocx.revisao_banco == banco.revisao,
        )
        .limit(1)
    )
    return (Marco.CONCLUIDO if exportado is not None else Marco.M10_DOCX), None


def marco_do_banco(db: Session, banco: BancoQuestoes) -> MarcoBanco:
    marco, motivo = classificar_banco(db, banco)
    # Excluída ocupa o número: a exclusão não abre lacuna, e reenviar a
    # geração não a preenche.
    ocupados = db.scalar(
        select(func.count(func.distinct(Questao.numero))).where(
            Questao.banco_id == banco.id
        )
    )
    objetivas_ativas = db.scalar(
        select(func.count())
        .select_from(Questao)
        .where(
            Questao.banco_id == banco.id,
            Questao.estado == EstadoQuestao.ATIVA,
            Questao.tipo == TipoQuestao.OBJETIVA,
        )
    )
    return MarcoBanco(
        versao=banco.versao,
        banco_id=banco.id,
        revisao=banco.revisao,
        marco=marco,
        motivo=motivo,
        n_alvo=banco.n_alvo,
        n_atual=banco.n_atual,
        lacunas=banco.n_alvo - ocupados,
        alerta_desvio=impacto_atual(db, banco).alerta_desvio,
        objetivas_ativas=objetivas_ativas,
        objetivas_auditadas=montar_resumo(db, banco).auditadas,
        comandos=list(COMANDOS[marco]),
        campos_prosseguir=list(CAMPOS_PROSSEGUIR[marco]),
    )


def marco_da_sessao(db: Session, sessao: SessaoGeracao) -> MarcoSessao:
    # Depois do M1 a sessão está sempre em M2: criar outro banco com versão
    # nova é sempre possível.
    marco = (
        Marco.M1_MATERIAIS if sessao.estado is EstadoSessao.RASCUNHO else Marco.M2_BANCO
    )
    n_materiais = db.scalar(
        select(func.count())
        .select_from(MaterialReferencia)
        .where(MaterialReferencia.sessao_id == sessao.id)
    )
    bancos = db.scalars(
        select(BancoQuestoes)
        .where(BancoQuestoes.sessao_id == sessao.id)
        .order_by(BancoQuestoes.id)
    )
    return MarcoSessao(
        sessao_id=sessao.id,
        marco=marco,
        n_materiais=n_materiais,
        comandos=list(COMANDOS[marco]),
        campos_prosseguir=list(CAMPOS_PROSSEGUIR[marco]),
        bancos=[marco_do_banco(db, banco) for banco in bancos],
    )
