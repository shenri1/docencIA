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
    FormatoItem,
    TipoEventoAuditoria,
    TipoQuestao,
)
from backend.app.exceptions import (
    CandidataPendenteException,
    EstadoQuestaoInvalidoException,
    QuestaoNaoEncontradaException,
    SemCandidataPendenteException,
    SubstituicaoAposMontagemException,
)
from backend.app.models.banco import (
    BancoQuestoes,
    Questao,
    RegistroSubstituicao,
    RelatorioImpacto,
)
from backend.app.models.identidade import Docente
from backend.app.models.provas import Prova
from backend.app.schemas.orientacao import DirecaoVariacao
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.controle_banco.estado import (
    exigir_revisao,
    registrar_relatorio,
    travar_banco,
)
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.geracao.banco_service import (
    Improdutiva,
    Produzida,
    produzir_questao,
)
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.orientacoes.orientacao_service import (
    criar_orientacao_questao,
    vigentes,
)
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
    substituição. Na discursiva, os aspectos esperados, pelo mesmo motivo."""
    linhas = [f"Enunciado: {questao.enunciado}"]
    if questao.tipo is TipoQuestao.OBJETIVA:
        for alternativa in sorted(questao.alternativas, key=lambda a: a.letra):
            linhas.append(f"{alternativa.letra}) {alternativa.texto}")
    else:
        for aspecto in sorted(questao.aspectos, key=lambda a: a.ordem):
            linhas.append(f"Aspecto esperado: {aspecto.texto}")
    return "\n".join(linhas)


_AVISO_REPETICAO = (
    "A tentativa anterior repetiu o enunciado desta questão. Pergunte outra "
    "coisa sobre os trechos."
)


def _pergunta(questao: Questao) -> str:
    """O enunciado sem o contexto. Variação que reaproveita o cenário
    e pergunta outra coisa não é cópia. Questão anterior à etapa, sem contexto
    gravado, compara o enunciado inteiro."""
    estrutura = (
        questao.justificativa.estrutura_formato if questao.justificativa else None
    )
    contexto = (estrutura or {}).get("contexto") or ""
    if contexto.strip():
        return questao.enunciado.removeprefix(f"{contexto}\n\n")
    return questao.enunciado


def _formato_da_original(questao: Questao):
    """(formato, configuração, n_itens) da original. Questão anterior à 
    é proposição sem itens."""
    estrutura = (
        questao.justificativa.estrutura_formato if questao.justificativa else None
    ) or {}
    configuracao = None
    if questao.formato is FormatoItem.AFIRMATIVAS:
        configuracao = tuple(a["verdadeira"] for a in estrutura["afirmativas"])
    elif questao.formato is FormatoItem.ASSERCAO_RAZAO:
        configuracao = estrutura["configuracao"]
    itens = {a.item for a in questao.aspectos if a.item is not None}
    return questao.formato, configuracao, (len(itens) or None)


def propor_substituicao(
    db: Session,
    embeddings,
    reranker,
    provedor,
    docente: Docente,
    banco: BancoQuestoes,
    numero: int,
    direcao: DirecaoVariacao | None = None,
) -> Produzida | Improdutiva:
    """Gera a candidata. NÃO muda o banco: nem revisão, nem n_atual, nem a
    original. Permitido com o banco aberto e congelado.

    Com direcao, é a variação guiada: a original vira questão de
    partida, e a orientação é gravada antes do modelo."""
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

    orientacoes = vigentes(db, sessao)
    if direcao is not None:
        # Gravada (e commitada) antes do modelo: a candidata aponta para ela, e
        # uma insuficiência deixa o registro de que o docente pediu e o material
        # não sustentou. O teto, se acumular, é checado aqui, antes da GPU.
        nova = criar_orientacao_questao(
            db,
            docente,
            banco,
            numero,
            direcao.cruzar_com,
            direcao.o_que_mudar,
            direcao.acumular,
        )
        # Vigentes primeiro, na ordem de criação, e a da variação por último.
        orientacoes = [*orientacoes, nova]

    # Mesma âncora => mesmos trechos, e o modelo tende a devolver o mesmo
    # enunciado mesmo instruído a não repetir (medido no qwen3:4b). A cópia é
    # medida no rascunho e ganha UMA nova tentativa, com o aviso explícito.
    evitar = _texto_a_evitar(original)
    formato, configuracao, n_itens = _formato_da_original(original)
    for tentativa in range(2):
        resultado = produzir_questao(
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
            evitar=evitar if tentativa == 0 else f"{evitar}\n\n{_AVISO_REPETICAO}",
            formato=formato,
            configuracao=configuracao,
            n_itens=n_itens,
            pergunta_original=_pergunta(original),
            orientacoes=orientacoes,
            partida=direcao is not None,
        )
        if not (isinstance(resultado, Improdutiva) and resultado.repetida):
            return resultado
    # duas cópias seguidas dizem que o trecho não rende outra questão.
    return Improdutiva(
        numero=numero,
        localizacao=resultado.localizacao,
        motivo="o material não sustentou uma variação diferente da original: "
        "as duas tentativas repetiram o enunciado",
    )


def aceitar_substituicao(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    numero: int,
    revisao_esperada: int,
) -> RelatorioImpacto:
    travar_banco(db, banco)
    exigir_revisao(banco, revisao_esperada)
    # Aceitar move a revisão do banco: com provas já montadas sobre ele, elas
    # ficariam desatualizadas e a exportação bloquearia de vez. Proposta e
    # rejeição não mexem no banco e seguem permitidas.
    montadas = list(db.scalars(select(Prova.versao).where(Prova.banco_id == banco.id)))
    if montadas:
        raise SubstituicaoAposMontagemException(sorted(montadas))
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
