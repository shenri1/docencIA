"""Substituição autorizada — orquestração de caso de uso.

"substituições são vetadas salvo comando explícito 'Autorizar
substituição de Qx'". Duas etapas de propósito: propor gera uma CANDIDATA fora
do banco, e o docente lê a questão inteira — inclusive a correta e as violações
de forma — antes de aceitar. Em uma etapa só, ele autorizaria a troca por uma
questão que ainda não viu.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import (
    DecisaoSubstituicao,
    EstadoQuestao,
    EventoBanco,
    TipoEventoAuditoria,
    TipoQuestao,
)
from backend.app.exceptions import (
    CandidataPendenteException,
    EstadoQuestaoInvalidoException,
    QuestaoNaoEncontradaException,
    SemCandidataPendenteException,
)
from backend.app.models.banco import (
    BancoQuestoes,
    Questao,
    RegistroSubstituicao,
    RelatorioImpacto,
)
from backend.app.models.identidade import Docente
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.controle_banco.estado import (
    exigir_revisao,
    registrar_relatorio,
)
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.geracao.banco_service import (
    Improdutiva,
    Produzida,
    produzir_questao,
)
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.prompt_mestre_service import verificar_integridade

# Estados que podem ser substituídos: a que está no banco e a que foi excluída.
_SUBSTITUIVEIS = (EstadoQuestao.ATIVA, EstadoQuestao.EXCLUIDA)


def _questao_por_numero(
    db: Session, banco: BancoQuestoes, numero: int, estados: tuple[EstadoQuestao, ...]
) -> Questao | None:
    return db.scalar(
        select(Questao).where(
            Questao.banco_id == banco.id,
            Questao.numero == numero,
            Questao.estado.in_(estados),
        )
    )


def _texto_a_evitar(questao: Questao) -> str:
    """O que o Gerador recebe como "não repita". Na objetiva vão também as
    alternativas: a mesma questão com as mesmas opções reordenadas não é uma
    substituição."""
    linhas = [f"Enunciado: {questao.enunciado}"]
    if questao.tipo is TipoQuestao.OBJETIVA:
        for alternativa in sorted(questao.alternativas, key=lambda a: a.letra):
            linhas.append(f"{alternativa.letra}) {alternativa.texto}")
    return "\n".join(linhas)


def propor_substituicao(
    db: Session,
    embeddings,
    reranker,
    provedor,
    docente: Docente,
    banco: BancoQuestoes,
    numero: int,
) -> Produzida | Improdutiva:
    """Gera a candidata. NÃO muda o banco: nem revisão, nem n_atual, nem a
    original. Permitido com o banco aberto e congelado."""
    # Checagens baratas antes do modelo: ~38 s de GPU por proposta.
    verificar_integridade(db)
    original = _questao_por_numero(db, banco, numero, _SUBSTITUIVEIS)
    if original is None:
        # Distingue "não existe" de "existe em estado que não aceita troca".
        qualquer = _questao_por_numero(db, banco, numero, tuple(EstadoQuestao))
        if qualquer is None:
            raise QuestaoNaoEncontradaException(numero)
        raise EstadoQuestaoInvalidoException(numero, qualquer.estado.value)
    if _questao_por_numero(db, banco, numero, (EstadoQuestao.CANDIDATA,)) is not None:
        raise CandidataPendenteException(numero)

    sessao = banco.sessao
    n_alvo_do_tipo = (
        banco.n_alvo_objetivas
        if original.tipo is TipoQuestao.OBJETIVA
        else banco.n_alvo_discursivas
    )
    distribuicao = calcular_distribuicao(
        n_alvo_do_tipo, sessao.p_f, sessao.p_m, sessao.p_d
    )
    # Mesma âncora da original: a seleção é determinística e o índice não muda
    # depois do índice confirmado, então numero-1 recupera o mesmo trecho.
    ancora = selecionar_ancoras(db, sessao, banco.n_alvo)[numero - 1]

    return produzir_questao(
        db,
        embeddings,
        reranker,
        provedor,
        sessao,
        banco,
        numero,
        original.tipo,
        original.faixa_dificuldade,
        ancora,
        distribuicao,
        estado=EstadoQuestao.CANDIDATA,
        evitar=_texto_a_evitar(original),
    )


def aceitar_substituicao(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    numero: int,
    revisao_esperada: int,
) -> RelatorioImpacto:
    exigir_revisao(banco, revisao_esperada)
    candidata = _questao_por_numero(db, banco, numero, (EstadoQuestao.CANDIDATA,))
    if candidata is None:
        raise SemCandidataPendenteException(numero)
    original = _questao_por_numero(db, banco, numero, _SUBSTITUIVEIS)
    if original is None:
        raise QuestaoNaoEncontradaException(numero)

    era_excluida = original.estado is EstadoQuestao.EXCLUIDA
    original.estado = EstadoQuestao.SUBSTITUIDA
    # O flush é obrigatório: sem ele o índice parcial veria dois ocupantes do
    # mesmo número na mesma instrução.
    db.flush()
    candidata.estado = EstadoQuestao.ATIVA
    if era_excluida:
        banco.n_atual += 1

    db.add(
        RegistroSubstituicao(
            questao_original_id=original.id,
            candidata_id=candidata.id,
            docente_id=docente.id,
            decisao=DecisaoSubstituicao.ACEITA,
        )
    )
    relatorio = registrar_relatorio(db, banco, EventoBanco.SUBSTITUICAO)
    registrar_evento(
        db,
        TipoEventoAuditoria.SUBSTITUICAO_ACEITA,
        f"bancos_questoes:{banco.id}",
        docente.id,
        {
            "numero": numero,
            "questao_original_id": original.id,
            "candidata_id": candidata.id,
            "revisao": banco.revisao,
        },
    )
    db.commit()
    return relatorio


def rejeitar_substituicao(
    db: Session, docente: Docente, banco: BancoQuestoes, numero: int
) -> Questao:
    """A candidata vira DESCARTADA e a rejeição fica gravada — é dado de
    pesquisa. O banco não muda: sem revisao_esperada, sem revisão nova, sem
    relatório."""
    candidata = _questao_por_numero(db, banco, numero, (EstadoQuestao.CANDIDATA,))
    if candidata is None:
        raise SemCandidataPendenteException(numero)
    original = _questao_por_numero(db, banco, numero, _SUBSTITUIVEIS)
    if original is None:
        raise QuestaoNaoEncontradaException(numero)

    candidata.estado = EstadoQuestao.DESCARTADA
    db.add(
        RegistroSubstituicao(
            questao_original_id=original.id,
            candidata_id=candidata.id,
            docente_id=docente.id,
            decisao=DecisaoSubstituicao.REJEITADA,
        )
    )
    registrar_evento(
        db,
        TipoEventoAuditoria.SUBSTITUICAO_REJEITADA,
        f"bancos_questoes:{banco.id}",
        docente.id,
        {
            "numero": numero,
            "questao_original_id": original.id,
            "candidata_id": candidata.id,
        },
    )
    db.commit()
    return candidata
