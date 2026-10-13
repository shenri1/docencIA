"""Agente Gerador — Núcleo Semântico.

Gera UMA questão a partir de uma âncora. O laço do banco é do banco_service:
aqui não há iteração, persistência nem transação.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.domain import FaixaDificuldade, FormatoItem, TipoQuestao
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial
from backend.app.prompt.montagem import montar_sistema
from backend.app.schemas.geracao import InsuficienciaFonte, montar_schema
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.geracao.contexto import (
    formatar_orientacoes,
    formatar_trechos,
    parametros_da_sessao,
)
from backend.app.services.geracao.formatos import (
    texto_contextualizacao,
    texto_pedido_formato,
    texto_pedido_itens,
)
from backend.app.services.provedor.tipos import RequisicaoLLM
from backend.app.services.rag.retrieval_service import TrechoRecuperado, buscar


@dataclass(frozen=True)
class ResultadoGeracao:
    numero: int
    questao: object | None
    motivo_insuficiencia: str | None
    localizacao_ancora: str
    # Os trechos enviados ao modelo: o crítico recebe exatamente os mesmos, e
    # as fontes só são resolvidas contra eles depois da revisão.
    trechos: list[TrechoRecuperado]
    # Qual modelo de fato respondeu — o fallback pode trocar entre chamadas.
    modelo: str


def _montar_usuario(
    trechos: list[TrechoRecuperado],
    faixa: FaixaDificuldade,
    k: int,
    tipo: TipoQuestao,
    evitar: str | None = None,
    formato: FormatoItem = FormatoItem.PROPOSICAO,
    configuracao=None,
    n_itens: int | None = None,
    orientacoes: Sequence = (),
    partida: bool = False,
) -> str:
    if tipo is TipoQuestao.DISCURSIVA:
        if n_itens is None:
            pedido = (
                f"Gere UMA questão discursiva de dificuldade {faixa.value}, com 2 a 5 "
                "aspectos esperados, cada um com a sua fonte, usando apenas os "
                "trechos acima."
            )
        else:
            pedido = (
                f"Gere UMA questão discursiva de dificuldade {faixa.value}, usando "
                f"apenas os trechos acima. {texto_pedido_itens(n_itens)}"
            )
    else:
        pedido = (
            f"Gere UMA questão de dificuldade {faixa.value}, usando apenas os trechos "
            f"acima. {texto_pedido_formato(formato, configuracao, k)}"
        )
    partes = ["Trechos disponíveis:\n" + formatar_trechos(trechos)]
    bloco = formatar_orientacoes(orientacoes)
    if bloco is not None:
        partes.append(bloco)
    if evitar is not None and partida:
        # Variação guiada: a original é ponto de partida, não coisa a
        # evitar. A cópia continua medida no rascunho pela pergunta.
        partes.append(
            "Questão de partida: mantenha o que funciona nela e aplique a "
            "orientação.\n" + evitar
        )
    elif evitar is not None:
        # A substituição reusa a MESMA âncora: sem esta instrução, a mesma
        # temperatura tenderia a devolver quase a mesma questão.
        partes.append(
            "Questão que está sendo substituída — não a repita. Escreva OUTRA "
            "questão: pergunte outra coisa sobre os trechos (outro aspecto, outra "
            "habilidade), e não a mesma pergunta com outras palavras.\n" + evitar
        )
    partes.append(texto_contextualizacao(faixa))
    partes.append(pedido)
    return "\n\n".join(partes)


def gerar_questao(
    db: Session,
    embeddings,
    reranker,
    provedor,
    sessao: SessaoGeracao,
    ancora: ChunkMaterial,
    faixa: FaixaDificuldade,
    numero: int,
    distribuicao: DistribuicaoQuestoes,
    tipo: TipoQuestao = TipoQuestao.OBJETIVA,
    evitar: str | None = None,
    formato: FormatoItem = FormatoItem.PROPOSICAO,
    configuracao=None,
    n_itens: int | None = None,
    trechos: list[TrechoRecuperado] | None = None,
    orientacoes: Sequence = (),
    partida: bool = False,
) -> ResultadoGeracao:
    # O texto da âncora É a consulta: ela já decidiu o assunto, e o RAG só
    # traz o contexto vizinho.
    # O recuo para proposição reusa os trechos já recuperados: sem novo embedding
    # nem as chamadas de rerank.
    if trechos is None:
        trechos = buscar(
            db,
            embeddings,
            reranker,
            sessao,
            ancora.texto,
            k=settings.rag_top_k,
            candidatos=settings.rag_candidatos,
        )

    sistema = montar_sistema(tipo, parametros_da_sessao(sessao, distribuicao), formato)

    resposta = provedor.gerar(
        sessao.id,
        RequisicaoLLM(
            sistema=sistema,
            usuario=_montar_usuario(
                trechos,
                faixa,
                sessao.k_alternativas,
                tipo,
                evitar,
                formato,
                configuracao,
                n_itens,
                orientacoes,
                partida,
            ),
            formato=montar_schema(
                tipo, sessao.k_alternativas, formato, configuracao, n_itens
            ),
            temperatura=settings.geracao_temperatura,
            max_tokens=settings.geracao_max_tokens,
        ),
    )

    conteudo = resposta.conteudo.resultado
    if isinstance(conteudo, InsuficienciaFonte):
        return ResultadoGeracao(
            numero=numero,
            questao=None,
            motivo_insuficiencia=conteudo.informacao_faltante,
            localizacao_ancora=ancora.localizacao,
            trechos=trechos,
            modelo=resposta.modelo,
        )

    return ResultadoGeracao(
        numero=numero,
        questao=conteudo,
        motivo_insuficiencia=None,
        localizacao_ancora=ancora.localizacao,
        trechos=trechos,
        modelo=resposta.modelo,
    )
