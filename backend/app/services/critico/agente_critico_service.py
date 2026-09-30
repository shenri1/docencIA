"""Agente Crítico, revisão na geração — Núcleo Semântico.

Uma chamada sem histórico: o mesmo modelo recebe os mesmos trechos, o próprio
rascunho e as violações de forma que o validador determinístico mediu, e
reemite a questão no mesmo schema. O determinístico guia o semântico; o
crítico não precisa descobrir o que o código já mediu.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.config import settings
from backend.app.domain import FaixaDificuldade, TipoQuestao
from backend.app.models.identidade import SessaoGeracao
from backend.app.prompt.montagem import montar_sistema_critico
from backend.app.schemas.geracao import (
    LETRAS,
    InsuficienciaFonte,
    montar_schema,
)
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.geracao.contexto import (
    formatar_trechos,
    parametros_da_sessao,
)
from backend.app.services.provedor.tipos import RequisicaoLLM
from backend.app.services.qualidade.validador_itens import (
    AlternativaAvaliavel,
    AspectoAvaliavel,
    ItemDiscursivo,
    ItemObjetivo,
    Violacao,
)
from backend.app.services.rag.retrieval_service import TrechoRecuperado


@dataclass(frozen=True)
class ResultadoRevisao:
    questao: object | None
    motivo_insuficiencia: str | None
    modelo: str


def item_objetivo_de(questao, trechos: list[TrechoRecuperado]) -> ItemObjetivo:
    """Mesma regra da persistência: letra por posição, correta pela letra."""
    return ItemObjetivo(
        enunciado=questao.enunciado,
        alternativas=[
            AlternativaAvaliavel(
                letra=letra,
                texto=alternativa.texto,
                correta=letra == questao.letra_correta,
                e_gemeo_malvado=alternativa.e_gemeo_malvado,
            )
            for letra, alternativa in zip(LETRAS, questao.alternativas, strict=False)
        ],
        trechos_base=[fonte.trecho_base for fonte in questao.fontes],
        identificadores_fonte=sorted({t.identificador_curto for t in trechos}),
        justificativa_correta=questao.justificativa.justificativa_correta,
        texto_verificacao_unicidade=questao.justificativa.texto_verificacao_unicidade,
        invalidacoes=[
            (i.letra, i.motivo) for i in questao.justificativa.invalidacao_distratores
        ],
    )


def item_discursivo_de(questao, trechos: list[TrechoRecuperado]) -> ItemDiscursivo:
    return ItemDiscursivo(
        enunciado=questao.enunciado,
        aspectos=[
            AspectoAvaliavel(texto=a.texto, trecho_base=a.fonte.trecho_base)
            for a in questao.aspectos_esperados
        ],
        identificadores_fonte=sorted({t.identificador_curto for t in trechos}),
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
) -> str:
    if tipo is TipoQuestao.DISCURSIVA:
        frase_final = (
            f"\n\nDevolva a questão revisada, de dificuldade {faixa.value}, com "
            "2 a 5 aspectos esperados, cada um com a sua fonte, usando apenas os "
            "trechos acima."
        )
    else:
        frase_final = (
            f"\n\nDevolva a questão revisada, de dificuldade {faixa.value}, com "
            f"exatamente {k} alternativas, usando apenas os trechos acima."
        )
    return (
        "Trechos disponíveis:\n"
        + formatar_trechos(trechos)
        + "\n\nRascunho a revisar (JSON):\n"
        + rascunho.model_dump_json(indent=2)
        + "\n\nViolações de forma medidas pelo sistema:\n"
        + _formatar_violacoes(violacoes)
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
) -> ResultadoRevisao:
    resposta = provedor.gerar(
        sessao.id,
        RequisicaoLLM(
            sistema=montar_sistema_critico(
                tipo, parametros_da_sessao(sessao, distribuicao)
            ),
            usuario=_montar_usuario(
                trechos, rascunho, violacoes, faixa, sessao.k_alternativas, tipo
            ),
            # Mesmo schema da geração: o crítico reemite a questão inteira, e
            # pode declarar insuficiência se concluir que ela não se sustenta.
            formato=montar_schema(tipo, sessao.k_alternativas),
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
        )
    return ResultadoRevisao(
        questao=conteudo, motivo_insuficiencia=None, modelo=resposta.modelo
    )
