"""Agente Crítico, revisão na geração — Núcleo Semântico.

Uma chamada sem histórico: o mesmo modelo recebe os mesmos trechos, o próprio
rascunho e as violações de forma que o validador determinístico mediu, e
reemite a questão no mesmo schema. O determinístico guia o semântico; o
crítico não precisa descobrir o que o código já mediu.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.core.config import settings
from backend.app.domain import FaixaDificuldade, FormatoItem, TipoQuestao
from backend.app.models.identidade import SessaoGeracao
from backend.app.prompt.montagem import montar_sistema_critico
from backend.app.schemas.geracao import (
    LETRAS,
    InsuficienciaFonte,
    montar_schema,
)
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.geracao.contexto import (
    formatar_orientacoes,
    formatar_trechos,
    parametros_da_sessao,
)
from backend.app.services.geracao.formatos import (
    LETRAS_ITEM,
    DiscursivaMontada,
    QuestaoMontada,
    texto_contextualizacao,
    texto_pedido_formato,
    texto_pedido_itens,
)
from backend.app.services.provedor.tipos import RequisicaoLLM, UsoTokens
from backend.app.services.qualidade.validador_itens import (
    AlternativaAvaliavel,
    AspectoAvaliavel,
    ItemDiscursivo,
    ItemObjetivo,
    Violacao,
)
from backend.app.services.rag.retrieval_service import TrechoRecuperado

_NAO_DESFAZER = "A revisão não desfaz o que as orientações pediram."


@dataclass(frozen=True)
class ResultadoRevisao:
    questao: object | None
    motivo_insuficiencia: str | None
    modelo: str
    # Para as métricas da tentativa.
    uso: UsoTokens | None = None


def item_objetivo_de(
    montada: QuestaoMontada,
    trechos: list[TrechoRecuperado],
    faixa: FaixaDificuldade | None = None,
) -> ItemObjetivo:
    """Mesma regra da persistência: letra por posição, correta pela letra."""
    calculo = (
        montada.estrutura_formato if montada.formato is FormatoItem.CALCULO else None
    )
    return ItemObjetivo(
        enunciado=montada.enunciado,
        alternativas=[
            AlternativaAvaliavel(
                letra=letra,
                texto=alternativa.texto,
                correta=letra == montada.letra_correta,
                e_gemeo_malvado=alternativa.e_gemeo_malvado,
            )
            for letra, alternativa in zip(LETRAS, montada.alternativas, strict=False)
        ],
        trechos_base=[fonte.trecho_base for fonte in montada.fontes],
        identificadores_fonte=sorted({t.identificador_curto for t in trechos}),
        justificativa_correta=montada.justificativa_correta,
        texto_verificacao_unicidade=montada.texto_verificacao_unicidade,
        invalidacoes=[(i.letra, i.motivo) for i in montada.invalidacoes],
        formato=montada.formato,
        faixa=faixa,
        contexto=montada.contexto,
        comando=montada.comando,
        assercoes=montada.assercoes,
        formula_citada=calculo["formula_citada"] if calculo else None,
        dados_calculo=(
            [(d["simbolo"], d["valor"], d["unidade"]) for d in calculo["dados"]]
            if calculo
            else None
        ),
        texto_dos_trechos=[t.texto for t in trechos] if calculo else None,
    )


def item_discursivo_de(
    montada: DiscursivaMontada,
    trechos: list[TrechoRecuperado],
    faixa: FaixaDificuldade | None = None,
) -> ItemDiscursivo:
    comandos = (
        None
        if montada.n_itens is None
        else [(f"item {LETRAS_ITEM[i]}", c) for i, c in enumerate(montada.comandos)]
    )
    return ItemDiscursivo(
        enunciado=montada.enunciado,
        aspectos=[
            AspectoAvaliavel(texto=a.texto, trecho_base=a.fonte.trecho_base)
            for a in montada.aspectos
        ],
        identificadores_fonte=sorted({t.identificador_curto for t in trechos}),
        faixa=faixa,
        contexto=montada.contexto,
        comandos=comandos,
    )


def _formatar_violacoes(violacoes: list[Violacao]) -> str:
    if not violacoes:
        return "Nenhuma violação de forma foi detectada."
    return "\n".join(f"- [{v.regra.value}] {v.alvo}: {v.detalhe}" for v in violacoes)


def _montar_usuario(
    trechos: list[TrechoRecuperado],
    rascunho,
    violacoes: list[Violacao],
    faixa: FaixaDificuldade,
    k: int,
    tipo: TipoQuestao,
    formato: FormatoItem = FormatoItem.PROPOSICAO,
    configuracao=None,
    n_itens: int | None = None,
    orientacoes: Sequence = (),
) -> str:
    if tipo is TipoQuestao.DISCURSIVA:
        if n_itens is None:
            pedido = (
                f"Devolva a questão revisada, de dificuldade {faixa.value}, com "
                "2 a 5 aspectos esperados, cada um com a sua fonte, usando apenas os "
                "trechos acima."
            )
        else:
            pedido = (
                f"Devolva a questão revisada, de dificuldade {faixa.value}, usando "
                f"apenas os trechos acima. {texto_pedido_itens(n_itens)}"
            )
    else:
        pedido = (
            f"Devolva a questão revisada, de dificuldade {faixa.value}, usando "
            f"apenas os trechos acima. {texto_pedido_formato(formato, configuracao, k)}"
        )
    frase_final = f"\n\n{texto_contextualizacao(faixa)}\n\n{pedido}"
    bloco = formatar_orientacoes(orientacoes)
    orientacoes_txt = "" if bloco is None else f"\n\n{bloco}\n{_NAO_DESFAZER}"
    return (
        "Trechos disponíveis:\n"
        + formatar_trechos(trechos)
        + "\n\nRascunho a revisar (JSON):\n"
        + rascunho.model_dump_json(indent=2)
        + "\n\nViolações de forma medidas pelo sistema:\n"
        + _formatar_violacoes(violacoes)
        + orientacoes_txt
        + frase_final
    )


def revisar_questao(
    provedor,
    sessao: SessaoGeracao,
    trechos: list[TrechoRecuperado],
    rascunho,
    violacoes: list[Violacao],
    faixa: FaixaDificuldade,
    distribuicao: DistribuicaoQuestoes,
    tipo: TipoQuestao = TipoQuestao.OBJETIVA,
    formato: FormatoItem = FormatoItem.PROPOSICAO,
    configuracao=None,
    n_itens: int | None = None,
    orientacoes: Sequence = (),
) -> ResultadoRevisao:
    resposta = provedor.gerar(
        sessao.id,
        RequisicaoLLM(
            sistema=montar_sistema_critico(
                tipo, parametros_da_sessao(sessao, distribuicao), formato
            ),
            usuario=_montar_usuario(
                trechos,
                rascunho,
                violacoes,
                faixa,
                sessao.k_alternativas,
                tipo,
                formato,
                configuracao,
                n_itens,
                orientacoes,
            ),
            # Mesmo schema da geração: o crítico reemite a questão inteira, e
            # pode declarar insuficiência se concluir que ela não se sustenta.
            # Fonte só entre os materiais destes trechos.
            formato=montar_schema(
                tipo,
                sessao.k_alternativas,
                formato,
                configuracao,
                n_itens,
                [t.identificador_curto for t in trechos],
            ),
            temperatura=settings.critico_temperatura,
            max_tokens=settings.critico_max_tokens,
        ),
    )
    conteudo = resposta.conteudo.resultado
    if isinstance(conteudo, InsuficienciaFonte):
        return ResultadoRevisao(
            questao=None,
            motivo_insuficiencia=conteudo.informacao_faltante,
            modelo=resposta.modelo,
            uso=resposta.uso,
        )
    return ResultadoRevisao(
        questao=conteudo,
        motivo_insuficiencia=None,
        modelo=resposta.modelo,
        uso=resposta.uso,
    )
