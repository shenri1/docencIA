"""Laço do banco — orquestração de caso de uso.

O commit é por questão, não por banco. Cada questão custa duas chamadas ao
modelo (Gerador + Crítico), cerca de 38 s; falha no meio preserva o que já foi
gerado, e chamar de novo continua de onde parou.

o banco passa a ser misto — objetivas e discursivas na mesma
chamada, cada tipo com o seu plano e a sua persistência.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    EstadoSessao,
    FaixaDificuldade,
    FormatoItem,
    NivelBloom,
    TipoEventoAuditoria,
    TipoQuestao,
)
from backend.app.exceptions import (
    BancoCongeladoException,
    FonteInvalidaException,
    GeracaoEmAndamentoException,
    ParametrosBancoDivergentesException,
    RespostaLLMInvalidaException,
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
from backend.app.models.orientacoes import OrientacaoDocente
from backend.app.schemas.geracao import LETRAS
from backend.app.services.calculo_distribuicao_service import (
    DistribuicaoQuestoes,
    calcular_distribuicao,
)
from backend.app.services.calculo_item.montagem import CalculoNaoMontavel
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
from backend.app.services.geracao.busca_orientada import trechos_com_orientacoes
from backend.app.services.geracao.contexto import resolver_fontes
from backend.app.services.geracao.plano_calculo import (
    contagens_de_calculo,
    posicoes_de_calculo,
)
from backend.app.services.geracao.formatos import (
    atribuir_configuracao,
    atribuir_formato,
    atribuir_n_itens,
    montar_discursiva,
    montar_objetiva,
)
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.metricas.coletor import Coletor
from backend.app.services.metricas.juiz import Juiz
from backend.app.services.metricas.registro import registrar_tentativa
from backend.app.services.orientacoes.orientacao_service import vigentes
from backend.app.services.prompt_mestre_service import verificar_integridade
from backend.app.services.qualidade.validador_itens import (
    Violacao,
    enunciado_repetido,
    validar_discursiva,
    validar_objetiva,
)
from backend.app.services.sessao_service import exigir_indice_confirmado

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Improdutiva:
    numero: int
    localizacao: str
    motivo: str
    # Só na substituição: o rascunho repetiu a original. Medido, não declarado
    # pelo modelo — por isso a substituição tenta de novo em vez de desistir.
    repetida: bool = False
    # Para as métricas: por que o número ficou sem questão.
    desfecho: str = "insuficiencia"


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
    # Geração em lotes. Tentar = chamar
    # produzir_questao, com resultado produzido ou improdutivo.
    ultimo_numero: int | None
    restantes: int


@dataclass(frozen=True)
class ItemPlano:
    numero: int
    tipo: TipoQuestao
    faixa: FaixaDificuldade
    distribuicao: DistribuicaoQuestoes
    formato: FormatoItem = FormatoItem.PROPOSICAO
    configuracao: tuple[bool, ...] | str | None = None
    n_itens: int | None = None


def _montar_plano(
    sessao: SessaoGeracao, n_objetivas: int, n_discursivas: int
) -> list[ItemPlano]:
    """Objetivas primeiro, depois discursivas, cada tipo em fácil → média →
    difícil com o seu próprio maior resto. numero == índice da âncora + 1: a
    seleção é determinística, então retomar é pular os que já existem. Formato,
    configuração e itens também são função pura da posição."""
    plano: list[ItemPlano] = []
    k = sessao.k_alternativas
    ordinais: dict[FormatoItem, int] = {}
    for tipo, n in (
        (TipoQuestao.OBJETIVA, n_objetivas),
        (TipoQuestao.DISCURSIVA, n_discursivas),
    ):
        if n == 0:
            continue
        distribuicao = calcular_distribuicao(n, sessao.p_f, sessao.p_m, sessao.p_d)
        calculo: dict[FaixaDificuldade, int] = {}
        if tipo is TipoQuestao.OBJETIVA and sessao.p_calculo > 0:
            itens = list(distribuicao.itens())
            calculo = dict(
                zip(
                    (faixa for faixa, _ in itens),
                    contagens_de_calculo(n, sessao.p_calculo, [q for _, q in itens]),
                    strict=True,
                )
            )
        for faixa, quantidade in distribuicao.itens():
            posicoes = posicoes_de_calculo(quantidade, calculo.get(faixa, 0))
            nao_calculo = 0
            for posicao in range(quantidade):
                numero = len(plano) + 1
                if tipo is TipoQuestao.DISCURSIVA:
                    plano.append(
                        ItemPlano(
                            numero,
                            tipo,
                            faixa,
                            distribuicao,
                            n_itens=atribuir_n_itens(faixa, posicao),
                        )
                    )
                    continue
                if posicao in posicoes:
                    # Espalhadas pela faixa; fora do rodízio e dos ordinais.
                    plano.append(
                        ItemPlano(
                            numero, tipo, faixa, distribuicao, FormatoItem.CALCULO, None
                        )
                    )
                    continue
                formato = atribuir_formato(faixa, nao_calculo, k)
                nao_calculo += 1
                ordinal = ordinais.get(formato, 0)
                ordinais[formato] = ordinal + 1
                plano.append(
                    ItemPlano(
                        numero,
                        tipo,
                        faixa,
                        distribuicao,
                        formato,
                        atribuir_configuracao(formato, ordinal, k),
                    )
                )
    return plano


def _obter_ou_criar_banco(
    db: Session,
    sessao: SessaoGeracao,
    versao: str,
    n_objetivas: int,
    n_discursivas: int,
) -> BancoQuestoes:
    consulta = select(BancoQuestoes).where(
        BancoQuestoes.sessao_id == sessao.id, BancoQuestoes.versao == versao
    )
    banco = db.scalar(consulta)
    if banco is None:
        sessao_id = sessao.id  # lido antes: o rollback abaixo expira `sessao`
        banco = BancoQuestoes(
            sessao_id=sessao_id,
            versao=versao,
            n_alvo=n_objetivas + n_discursivas,
            n_alvo_objetivas=n_objetivas,
            n_alvo_discursivas=n_discursivas,
            n_atual=0,
        )
        db.add(banco)
        try:
            db.commit()
        except IntegrityError:
            # Outra requisição criou o mesmo banco entre a leitura e o INSERT
            # (banco_por_sessao_versao). Segue com o dela: as checagens de
            # estado e de parâmetros abaixo valem igual.
            db.rollback()
            banco = db.scalar(consulta)
            if banco is None:
                raise
        else:
            db.refresh(banco)
            return banco
    if banco.estado is EstadoBanco.CONGELADO:
        # Congelado não recebe questão nova.
        raise BancoCongeladoException(versao)
    if (banco.n_alvo_objetivas, banco.n_alvo_discursivas) != (
        n_objetivas,
        n_discursivas,
    ):
        raise ParametrosBancoDivergentesException(
            versao,
            gravado=(banco.n_alvo_objetivas, banco.n_alvo_discursivas),
            pedido=(n_objetivas, n_discursivas),
        )
    return banco


def _montar(tipo: TipoQuestao, saida, formato, configuracao, k, numero):
    if tipo is TipoQuestao.OBJETIVA:
        return montar_objetiva(saida, formato, configuracao, k, numero)
    return montar_discursiva(saida)


def _montar_ou_bloqueio(tipo, saida, formato, configuracao, k, numero):
    """(montada, []) ou (None, violações que impediram a montagem). Só o
    formato CALCULO levanta: nos outros a montagem é total."""
    try:
        return _montar(tipo, saida, formato, configuracao, k, numero), []
    except CalculoNaoMontavel as exc:
        return None, exc.violacoes


def _validar(tipo: TipoQuestao, montada, trechos, faixa) -> list[Violacao]:
    if tipo is TipoQuestao.OBJETIVA:
        return validar_objetiva(item_objetivo_de(montada, trechos, faixa))
    return validar_discursiva(item_discursivo_de(montada, trechos, faixa))


def _persistir(
    db: Session,
    banco: BancoQuestoes,
    numero: int,
    tipo: TipoQuestao,
    faixa: FaixaDificuldade,
    final,
    formato_planejado: FormatoItem,
    resultado: ResultadoGeracao,
    revisao: ResultadoRevisao,
    violacoes_rascunho: list[Violacao],
    violacoes_final: list[Violacao],
    estado: EstadoQuestao,
    orientacoes: Sequence[OrientacaoDocente] = (),
    motivo_recuo: str | None = None,
    violacoes_recuo: Sequence[Violacao] = (),
) -> Questao:
    # `final` é a forma montada da versão revisada. Antes de qualquer db.add: fonte inválida levanta sem deixar objeto
    # pendente na sessão. Só a versão revisada vira FonteInterna.
    if tipo is TipoQuestao.OBJETIVA:
        # Objetiva — como hoje: uma FonteInterna por item de `final.fontes`,
        # sem dedup, na ordem original.
        unicas = resolver_fontes(final.fontes, resultado.trechos)
    else:
        chaves_por_aspecto = resolver_fontes(
            [a.fonte for a in final.aspectos], resultado.trechos
        )
        # Dois aspectos citando o mesmo trecho viram uma FonteInterna só.
        unicas = list(dict.fromkeys(chaves_por_aspecto))

    questao = Questao(
        banco_id=banco.id,
        numero=numero,
        tipo=tipo,
        formato=final.formato
        if tipo is TipoQuestao.OBJETIVA
        else FormatoItem.PROPOSICAO,
        enunciado=final.enunciado,
        nivel_bloom=NivelBloom(final.nivel_bloom),
        faixa_dificuldade=faixa,
        tema=final.tema,
        subtema=final.subtema,
        estado=estado,
    )
    # As orientações vigentes nesta geração, na mesma transação.
    questao.orientacoes = list(orientacoes)
    db.add(questao)
    versao = banco.versao  # lido antes: o rollback expira `banco`
    try:
        db.flush()  # precisa do id para os filhos
    except IntegrityError as exc:
        # Índice parcial questao_por_banco_numero_ocupado: outra requisição
        # (retry do cliente após timeout) gravou este número primeiro.
        db.rollback()
        raise GeracaoEmAndamentoException(versao, numero) from exc

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
        db.add(
            JustificativaEstruturada(
                questao_id=questao.id,
                objetivo_cognitivo=final.objetivo_cognitivo,
                justificativa_correta=final.justificativa_correta,
                invalidacao_distratores=[
                    {"letra": i.letra, "motivo": i.motivo} for i in final.invalidacoes
                ],
                verificacao_unicidade=final.verificacao_unicidade,
                texto_verificacao_unicidade=final.texto_verificacao_unicidade,
                estrutura_formato=final.estrutura_formato,
            )
        )
    else:
        for ordem, (aspecto, chave) in enumerate(
            zip(final.aspectos, chaves_por_aspecto, strict=True), start=1
        ):
            db.add(
                AspectoEsperado(
                    questao_id=questao.id,
                    ordem=ordem,
                    item=aspecto.item,
                    texto=aspecto.texto,
                    fonte_interna_id=fontes_por_chave[chave].id,
                )
            )
        db.add(
            JustificativaEstruturada(
                questao_id=questao.id,
                objetivo_cognitivo=final.objetivo_cognitivo,
                estrutura_formato={"contexto": final.contexto},
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
        # Incremento no SQL, sem lock do banco: `+= 1` em Python lê e grava, e
        # duas gerações concorrentes perderiam uma contagem.
        banco.n_atual = BancoQuestoes.n_atual + 1
    registrar_evento(
        db,
        TipoEventoAuditoria.QUESTAO_GERADA,
        f"questoes:{questao.id}",
        banco.sessao.docente_id,
        {
            "banco_id": banco.id,
            "numero": numero,
            "tipo": tipo.value,
            "formato_planejado": formato_planejado.value,
            "formato": questao.formato.value,
            "estado": estado.value,
            "modelo_geracao": resultado.modelo,
            "modelo_revisao": revisao.modelo,
            "n_violacoes_final": len(violacoes_final),
            "n_orientacoes": len(orientacoes),
            "com_cruzamento": any(o.cruzar_com for o in orientacoes),
            "orientacoes_ids": [o.id for o in orientacoes],
            # Por que o formato planejado não saiu ("insuficiencia"
            # ou "calculo"); None quando saiu.
            "motivo_recuo": motivo_recuo,
            # O que impediu o cálculo de montar depois do crítico. Só o enum: o
            # detalhe (símbolo, operação, unidade) vai para o log da aplicação.
            "violacoes_recuo": [v.regra.value for v in violacoes_recuo],
        },
    )
    db.commit()
    return questao


def _produzir_questao(
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
    formato: FormatoItem = FormatoItem.PROPOSICAO,
    configuracao=None,
    n_itens: int | None = None,
    pergunta_original: str | None = None,
    orientacoes: Sequence[OrientacaoDocente] = (),
    partida: bool = False,
    coletor: Coletor | None = None,
) -> Produzida | Improdutiva:
    """Uma questão, do rascunho ao commit: gerar, montar, medir, revisar, montar,
    medir, persistir. `gerar_banco` chama em laço; `propor_substituicao` chama uma
    vez. A sequência existe só aqui."""
    if coletor is None:
        coletor = Coletor()
    # A busca combinada sai daqui, uma vez: o recuo para proposição e o crítico
    # recebem os mesmos trechos.
    trechos = trechos_com_orientacoes(
        db, embeddings, reranker, sessao, ancora, orientacoes, coletor
    )
    formato_planejado = formato
    # Até duas tentativas: o formato planejado e, se ele não sair, a proposição
    # com os mesmos trechos. A âncora do número é fixa: insistir no mesmo formato
    # falharia em toda retomada.
    tentativas = [(formato, configuracao)]
    if tipo is TipoQuestao.OBJETIVA and formato is not FormatoItem.PROPOSICAO:
        tentativas.append((FormatoItem.PROPOSICAO, None))
    motivo_recuo: str | None = None
    violacoes_recuo: list[Violacao] = []
    k = sessao.k_alternativas

    for indice, (formato, configuracao) in enumerate(tentativas):
        ultima = indice == len(tentativas) - 1
        with coletor.medir("gerador", formato):
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
                formato=formato,
                configuracao=configuracao,
                n_itens=n_itens,
                trechos=trechos,
                orientacoes=orientacoes,
                partida=partida,
            )
        if resultado.uso is not None:
            coletor.anotar_tokens("gerador", resultado.uso, resultado.modelo, formato)
        coletor.modelo_geracao = resultado.modelo
        trechos = resultado.trechos
        coletor.trechos_enviados = trechos
        if resultado.questao is None:
            if not ultima:
                motivo_recuo = coletor.motivo_recuo = "insuficiencia"
                continue
            return Improdutiva(
                numero=numero,
                localizacao=resultado.localizacao_ancora,
                motivo=resultado.motivo_insuficiencia or "sem motivo declarado",
            )
        rascunho, bloqueio = _montar_ou_bloqueio(
            tipo, resultado.questao, formato, configuracao, k, numero
        )
        if rascunho is not None:
            if pergunta_original is not None and enunciado_repetido(
                rascunho.pergunta, pergunta_original
            ):
                # Medido no rascunho: revisar uma cópia gastaria o crítico à toa.
                return Improdutiva(
                    numero=numero,
                    localizacao=resultado.localizacao_ancora,
                    motivo="o rascunho repetiu o enunciado da questão original",
                    repetida=True,
                    desfecho="repetida",
                )
            # O determinístico mede, o semântico revisa com essa medida
            # como feedback, e o determinístico mede de novo, sempre sobre a
            # forma montada.
            with coletor.medir("validacao"):
                violacoes_rascunho = _validar(tipo, rascunho, trechos, faixa)
        else:
            # Cálculo que não monta: o que impediu vai ao crítico.
            violacoes_rascunho = bloqueio
        with coletor.medir("critico", formato):
            revisao = revisar_questao(
                provedor,
                sessao,
                trechos,
                resultado.questao,
                violacoes_rascunho,
                faixa,
                distribuicao,
                tipo=tipo,
                formato=formato,
                configuracao=configuracao,
                n_itens=n_itens,
                orientacoes=orientacoes,
            )
        if revisao.uso is not None:
            coletor.anotar_tokens("critico", revisao.uso, revisao.modelo, formato)
        coletor.modelo_revisao = revisao.modelo
        if revisao.questao is None:
            # O crítico concluiu que o material não sustenta a questão: 
            # funcionando. Nada é persistido, e a retomada tenta de novo.
            return Improdutiva(
                numero=numero,
                localizacao=resultado.localizacao_ancora,
                motivo="revisão: "
                + (revisao.motivo_insuficiencia or "sem motivo declarado"),
            )
        final, bloqueio_final = _montar_ou_bloqueio(
            tipo, revisao.questao, formato, configuracao, k, numero
        )
        if final is None:
            if not ultima:
                motivo_recuo = coletor.motivo_recuo = "calculo"
                violacoes_recuo = bloqueio_final
                # A tentativa recuada não é persistida: sem isto, o porquê some.
                _log.warning(
                    "questão %s do banco %s não montou em %s e recuou: %s",
                    numero,
                    banco.id,
                    formato.value,
                    "; ".join(f"{v.alvo}: {v.detalhe}" for v in bloqueio_final),
                )
                continue
            return Improdutiva(
                numero=numero,
                localizacao=resultado.localizacao_ancora,
                motivo="não montou: "
                + "; ".join(f"{v.alvo}: {v.detalhe}" for v in bloqueio_final),
                desfecho="nao_montou",
            )
        with coletor.medir("validacao"):
            violacoes_final = _validar(tipo, final, trechos, faixa)
        questao = _persistir(
            db,
            banco,
            numero,
            tipo,
            faixa,
            final,
            formato_planejado,
            resultado,
            revisao,
            violacoes_rascunho,
            violacoes_final,
            estado,
            orientacoes,
            motivo_recuo,
            violacoes_recuo,
        )
        coletor.formato_final = formato
        return Produzida(questao=questao, violacoes_final=violacoes_final)
    raise AssertionError("a última tentativa sempre retorna")  # pragma: no cover


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
    juiz: Juiz | None = None,
    **resto,
) -> Produzida | Improdutiva:
    """Falha do CONTEÚDO de uma questão não pára o banco: fonte que o modelo
    inventou ou resposta fora do formato viram lacuna daquele número, e o laço
    segue. As duas acontecem antes de qualquer gravação, então nada fica pela
    metade. Falha de infraestrutura (cadeia de provedores fora do ar, servidor
    ocupado, prompt divergente) continua subindo: seguir só faria todos os
    números seguintes falharem igual.

    Cada tentativa que termina, com ou sem questão, deixa uma linha de métricas
gravada depois do commit da questão. Falha de infraestrutura não
    deixa linha: ela já fica no evento `falha_provedor`."""
    coletor = Coletor()
    try:
        produzida = _produzir_questao(
            db,
            embeddings,
            reranker,
            provedor,
            sessao,
            banco,
            numero,
            tipo,
            faixa,
            ancora,
            distribuicao,
            coletor=coletor,
            **resto,
        )
    except FonteInvalidaException as exc:
        produzida = Improdutiva(
            numero=numero,
            localizacao=ancora.localizacao,
            motivo=str(exc),
            desfecho="fonte_invalida",
        )
    except RespostaLLMInvalidaException as exc:
        produzida = Improdutiva(
            numero=numero,
            localizacao=ancora.localizacao,
            motivo=str(exc),
            desfecho="resposta_invalida",
        )
    registrar_tentativa(
        db,
        coletor=coletor,
        banco=banco,
        sessao=sessao,
        numero=numero,
        tipo=tipo,
        faixa=faixa,
        formato_planejado=resto.get("formato", FormatoItem.PROPOSICAO),
        estado=resto.get("estado", EstadoQuestao.ATIVA),
        produzida=produzida,
        embeddings=embeddings,
        juiz=juiz,
    )
    return produzida


def gerar_banco(
    db: Session,
    embeddings,
    reranker,
    provedor,
    sessao: SessaoGeracao,
    n_objetivas: int,
    n_discursivas: int,
    versao: str,
    apos: int = 0,
    limite: int | None = None,
    juiz: Juiz | None = None,
) -> ResumoBanco:
    n_alvo = n_objetivas + n_discursivas
    if n_alvo < 1:
        # Erro de programação, porque a API já barra isso no schema.
        raise ValueError("banco precisa de ao menos uma questão")

    # Verificações baratas primeiro: descobrir material insuficiente no minuto
    # 7 desperdiçaria minutos de GPU.
    verificar_integridade(db)
    exigir_indice_confirmado(sessao)
    # Lidas uma vez por pedido: duas questões do mesmo lote recebem as mesmas.
    orientacoes = vigentes(db, sessao)
    banco = _obter_ou_criar_banco(db, sessao, versao, n_objetivas, n_discursivas)
    ancoras = selecionar_ancoras(db, sessao, n_alvo)

    plano = _montar_plano(sessao, n_objetivas, n_discursivas)

    ja_existentes = set(
        db.scalars(select(Questao.numero).where(Questao.banco_id == banco.id))
    )

    pendentes = [
        item
        for item in plano
        if item.numero > apos and item.numero not in ja_existentes
    ]
    tentar = pendentes if limite is None else pendentes[:limite]

    geradas = 0
    geradas_por_tipo: dict[TipoQuestao, int] = {
        TipoQuestao.OBJETIVA: 0,
        TipoQuestao.DISCURSIVA: 0,
    }
    improdutivas: list[Improdutiva] = []
    com_violacoes: list[ItemComViolacao] = []
    for item in tentar:
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
            formato=item.formato,
            configuracao=item.configuracao,
            n_itens=item.n_itens,
            orientacoes=orientacoes,
            juiz=juiz,
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
        ultimo_numero=tentar[-1].numero if tentar else None,
        restantes=len(pendentes) - len(tentar),
    )
