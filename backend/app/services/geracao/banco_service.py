"""Laço do banco — orquestração de caso de uso.

O commit é por questão, não por banco. Cada questão custa duas chamadas ao
modelo (Gerador + Crítico), cerca de 38 s; falha no meio preserva o que já foi
gerado, e chamar de novo continua de onde parou.

o banco passa a ser misto — objetivas e discursivas na mesma
chamada, cada tipo com o seu plano e a sua persistência.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    EstadoSessao,
    FaixaDificuldade,
    NivelBloom,
    TipoQuestao,
)
from backend.app.exceptions import (
    BancoCongeladoException,
    ParametrosBancoDivergentesException,
)
from backend.app.models.banco import (
    Alternativa,
    AspectoEsperado,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RevisaoQuestao,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial
from backend.app.schemas.geracao import LETRAS
from backend.app.services.calculo_distribuicao_service import (
    DistribuicaoQuestoes,
    calcular_distribuicao,
)
from backend.app.services.critico.agente_critico_service import (
    ResultadoRevisao,
    item_discursivo_de,
    item_objetivo_de,
    revisar_questao,
)
from backend.app.services.geracao.agente_gerador_service import (
    ResultadoGeracao,
    gerar_questao,
)
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.geracao.contexto import resolver_fontes
from backend.app.services.prompt_mestre_service import verificar_integridade
from backend.app.services.qualidade.validador_itens import (
    Violacao,
    validar_discursiva,
    validar_objetiva,
)
from backend.app.services.sessao_service import exigir_indice_confirmado


@dataclass(frozen=True)
class Improdutiva:
    numero: int
    localizacao: str
    motivo: str


@dataclass(frozen=True)
class Produzida:
    questao: Questao
    violacoes_final: list[Violacao]


@dataclass(frozen=True)
class ItemComViolacao:
    numero: int
    violacoes: list[Violacao]


@dataclass(frozen=True)
class ResumoBanco:
    banco_id: int
    # A revisão que o docente precisa mandar de volta no primeiro comando de
    # controle do banco.
    revisao: int
    geradas: int
    ja_existentes: int
    improdutivas: list[Improdutiva]
    # Violações que sobreviveram à revisão. É por aqui que o docente sabe
    # quais questões olhar antes da janela de exclusões.
    com_violacoes: list[ItemComViolacao]
    geradas_por_tipo: dict[TipoQuestao, int]


@dataclass(frozen=True)
class ItemPlano:
    numero: int
    tipo: TipoQuestao
    faixa: FaixaDificuldade
    distribuicao: DistribuicaoQuestoes


def _montar_plano(
    sessao: SessaoGeracao, n_objetivas: int, n_discursivas: int
) -> list[ItemPlano]:
    """Objetivas primeiro, depois discursivas, cada tipo em fácil → média →
    difícil com o seu próprio maior resto. numero == índice da âncora + 1: a
    seleção é determinística, então retomar é pular os que já existem."""
    plano: list[ItemPlano] = []
    for tipo, n in (
        (TipoQuestao.OBJETIVA, n_objetivas),
        (TipoQuestao.DISCURSIVA, n_discursivas),
    ):
        if n == 0:
            continue
        distribuicao = calcular_distribuicao(n, sessao.p_f, sessao.p_m, sessao.p_d)
        for faixa, quantidade in distribuicao.itens():
            # `base` ligado ANTES do extend — ver o comentário.
            base = len(plano)
            plano.extend(
                ItemPlano(base + i + 1, tipo, faixa, distribuicao)
                for i in range(quantidade)
            )
    return plano


def _obter_ou_criar_banco(
    db: Session, sessao: SessaoGeracao, versao: str, n_objetivas: int, n_discursivas: int
) -> BancoQuestoes:
    banco = db.scalar(
        select(BancoQuestoes).where(
            BancoQuestoes.sessao_id == sessao.id, BancoQuestoes.versao == versao
        )
    )
    if banco is None:
        banco = BancoQuestoes(
            sessao_id=sessao.id,
            versao=versao,
            n_alvo=n_objetivas + n_discursivas,
            n_alvo_objetivas=n_objetivas,
            n_alvo_discursivas=n_discursivas,
            n_atual=0,
        )
        db.add(banco)
        db.commit()
        db.refresh(banco)
        return banco
    if banco.estado is EstadoBanco.CONGELADO:
        # congelado não recebe questão nova.
        raise BancoCongeladoException(versao)
    if (banco.n_alvo_objetivas, banco.n_alvo_discursivas) != (n_objetivas, n_discursivas):
        raise ParametrosBancoDivergentesException(
            versao,
            gravado=(banco.n_alvo_objetivas, banco.n_alvo_discursivas),
            pedido=(n_objetivas, n_discursivas),
        )
    return banco


def _validar(tipo: TipoQuestao, questao, trechos) -> list[Violacao]:
    if tipo is TipoQuestao.OBJETIVA:
        return validar_objetiva(item_objetivo_de(questao, trechos))
    return validar_discursiva(item_discursivo_de(questao, trechos))


def _persistir(
    db: Session,
    banco: BancoQuestoes,
    numero: int,
    tipo: TipoQuestao,
    faixa: FaixaDificuldade,
    resultado: ResultadoGeracao,
    revisao: ResultadoRevisao,
    violacoes_rascunho: list[Violacao],
    violacoes_final: list[Violacao],
    estado: EstadoQuestao,
) -> Questao:
    final = revisao.questao
    # Antes de qualquer db.add: fonte inválida levanta sem deixar objeto
    # pendente na sessão. Só a versão revisada vira FonteInterna.
    if tipo is TipoQuestao.OBJETIVA:
        # Objetiva — como hoje: uma FonteInterna por item de `final.fontes`,
        # sem dedup, na ordem original.
        unicas = resolver_fontes(final.fontes, resultado.trechos)
    else:
        chaves_por_aspecto = resolver_fontes(
            [a.fonte for a in final.aspectos_esperados], resultado.trechos
        )
        # Dois aspectos citando o mesmo trecho viram uma FonteInterna só.
        unicas = list(dict.fromkeys(chaves_por_aspecto))

    questao = Questao(
        banco_id=banco.id,
        numero=numero,
        tipo=tipo,
        enunciado=final.enunciado,
        nivel_bloom=NivelBloom(final.nivel_bloom),
        faixa_dificuldade=faixa,
        tema=final.tema,
        subtema=final.subtema,
        estado=estado,
    )
    db.add(questao)
    db.flush()  # precisa do id para os filhos

    fontes_por_chave: dict[tuple[int, str, str], FonteInterna] = {}
    for chave in unicas:
        material_id, localizacao, trecho = chave
        fonte = FonteInterna(
            questao_id=questao.id,
            material_id=material_id,
            localizacao=localizacao,
            trecho_base=trecho,
        )
        db.add(fonte)
        fontes_por_chave[chave] = fonte
    db.flush()  # ids das fontes, para os aspectos

    if tipo is TipoQuestao.OBJETIVA:
        for letra, alternativa in zip(LETRAS, final.alternativas, strict=False):
            db.add(
                Alternativa(
                    questao_id=questao.id,
                    letra=letra,
                    texto=alternativa.texto,
                    correta=letra == final.letra_correta,
                    e_gemeo_malvado=alternativa.e_gemeo_malvado,
                )
            )
        justificativa = final.justificativa
        db.add(
            JustificativaEstruturada(
                questao_id=questao.id,
                objetivo_cognitivo=justificativa.objetivo_cognitivo,
                justificativa_correta=justificativa.justificativa_correta,
                invalidacao_distratores=[
                    i.model_dump() for i in justificativa.invalidacao_distratores
                ],
                verificacao_unicidade=justificativa.verificacao_unicidade,
                texto_verificacao_unicidade=justificativa.texto_verificacao_unicidade,
            )
        )
    else:
        for ordem, (aspecto, chave) in enumerate(
            zip(final.aspectos_esperados, chaves_por_aspecto, strict=True), start=1
        ):
            db.add(
                AspectoEsperado(
                    questao_id=questao.id,
                    ordem=ordem,
                    texto=aspecto.texto,
                    fonte_interna_id=fontes_por_chave[chave].id,
                )
            )
        db.add(
            JustificativaEstruturada(
                questao_id=questao.id,
                objetivo_cognitivo=final.objetivo_cognitivo,
            )
        )

    db.add(
        RevisaoQuestao(
            questao_id=questao.id,
            rascunho=resultado.questao.model_dump(mode="json"),
            violacoes_rascunho=[v.como_dict() for v in violacoes_rascunho],
            violacoes_final=[v.como_dict() for v in violacoes_final],
            modelo_geracao=resultado.modelo,
            modelo_revisao=revisao.modelo,
        )
    )
    if estado is EstadoQuestao.ATIVA:
        # Candidata não está no banco: n_atual conta só as ATIVA.
        banco.n_atual += 1
    db.commit()
    return questao


def produzir_questao(
    db: Session,
    embeddings,
    reranker,
    provedor,
    sessao: SessaoGeracao,
    banco: BancoQuestoes,
    numero: int,
    tipo: TipoQuestao,
    faixa: FaixaDificuldade,
    ancora: ChunkMaterial,
    distribuicao: DistribuicaoQuestoes,
    estado: EstadoQuestao = EstadoQuestao.ATIVA,
    evitar: str | None = None,
) -> Produzida | Improdutiva:
    """Uma questão, do rascunho ao commit: gerar, medir, revisar, medir,
    persistir. `gerar_banco` chama em laço; `propor_substituicao` chama uma vez.
    A sequência existe só aqui."""
    resultado = gerar_questao(
        db,
        embeddings,
        reranker,
        provedor,
        sessao,
        ancora,
        faixa,
        numero,
        distribuicao,
        tipo=tipo,
        evitar=evitar,
    )
    if resultado.questao is None:
        return Improdutiva(
            numero=numero,
            localizacao=resultado.localizacao_ancora,
            motivo=resultado.motivo_insuficiencia or "sem motivo declarado",
        )

    # o determinístico mede, o semântico revisa com essa medida como
    # feedback, e o determinístico mede de novo.
    violacoes_rascunho = _validar(tipo, resultado.questao, resultado.trechos)
    revisao = revisar_questao(
        provedor,
        sessao,
        resultado.trechos,
        resultado.questao,
        violacoes_rascunho,
        faixa,
        distribuicao,
        tipo=tipo,
    )
    if revisao.questao is None:
        # O crítico concluiu que o material não sustenta a questão: 
        # funcionando. Nada é persistido, e a retomada tenta de novo.
        return Improdutiva(
            numero=numero,
            localizacao=resultado.localizacao_ancora,
            motivo="revisão: "
            + (revisao.motivo_insuficiencia or "sem motivo declarado"),
        )

    violacoes_final = _validar(tipo, revisao.questao, resultado.trechos)
    questao = _persistir(
        db,
        banco,
        numero,
        tipo,
        faixa,
        resultado,
        revisao,
        violacoes_rascunho,
        violacoes_final,
        estado,
    )
    return Produzida(questao=questao, violacoes_final=violacoes_final)


def gerar_banco(
    db: Session,
    embeddings,
    reranker,
    provedor,
    sessao: SessaoGeracao,
    n_objetivas: int,
    n_discursivas: int,
    versao: str,
) -> ResumoBanco:
    n_alvo = n_objetivas + n_discursivas
    if n_alvo < 1:
        # Erro de programação, porque a API já barra isso no schema.
        raise ValueError("banco precisa de ao menos uma questão")

    # Verificações baratas primeiro: descobrir material insuficiente no minuto
    # 7 desperdiçaria minutos de GPU.
    verificar_integridade(db)
    exigir_indice_confirmado(sessao)
    banco = _obter_ou_criar_banco(db, sessao, versao, n_objetivas, n_discursivas)
    ancoras = selecionar_ancoras(db, sessao, n_alvo)

    plano = _montar_plano(sessao, n_objetivas, n_discursivas)

    ja_existentes = set(
        db.scalars(select(Questao.numero).where(Questao.banco_id == banco.id))
    )

    geradas = 0
    geradas_por_tipo: dict[TipoQuestao, int] = {
        TipoQuestao.OBJETIVA: 0,
        TipoQuestao.DISCURSIVA: 0,
    }
    improdutivas: list[Improdutiva] = []
    com_violacoes: list[ItemComViolacao] = []
    for item in plano:
        if item.numero in ja_existentes:
            continue
        produzida = produzir_questao(
            db,
            embeddings,
            reranker,
            provedor,
            sessao,
            banco,
            item.numero,
            item.tipo,
            item.faixa,
            ancoras[item.numero - 1],
            item.distribuicao,
        )
        if isinstance(produzida, Improdutiva):
            improdutivas.append(produzida)
            continue
        geradas += 1
        geradas_por_tipo[item.tipo] += 1
        if produzida.violacoes_final:
            com_violacoes.append(
                ItemComViolacao(item.numero, produzida.violacoes_final)
            )

    # A sessão nunca saía de MATERIAIS_CONFIRMADOS. As guardas de índice e
    # material testam `!= RASCUNHO`, então a retomada e o RAG continuam
    # funcionando depois disto.
    if banco.n_atual > 0 and sessao.estado is EstadoSessao.MATERIAIS_CONFIRMADOS:
        sessao.estado = EstadoSessao.BANCO_GERADO
        db.commit()

    return ResumoBanco(
        banco_id=banco.id,
        revisao=banco.revisao,
        geradas=geradas,
        ja_existentes=len(ja_existentes),
        improdutivas=improdutivas,
        com_violacoes=com_violacoes,
        geradas_por_tipo=geradas_por_tipo,
    )
