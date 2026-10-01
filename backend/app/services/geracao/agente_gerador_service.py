"""Agente Gerador — Núcleo Semântico.

Gera UMA questão a partir de uma âncora. O laço do banco é do banco_service:
aqui não há iteração, persistência nem transação.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.domain import FaixaDificuldade, TipoQuestao
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial
from backend.app.prompt.montagem import montar_sistema
from backend.app.schemas.geracao import InsuficienciaFonte, montar_schema
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.geracao.contexto import formatar_trechos, parametros_da_sessao
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
) -> str:
    if tipo is TipoQuestao.DISCURSIVA:
        pedido = (
            f"Gere UMA questão discursiva de dificuldade {faixa.value}, com 2 a 5 "
            "aspectos esperados, cada um com a sua fonte, usando apenas os "
            "trechos acima."
        )
    else:
        pedido = (
            f"Gere UMA questão de dificuldade {faixa.value} com exatamente {k} "
            "alternativas, usando apenas os trechos acima."
        )
    partes = ["Trechos disponíveis:\n" + formatar_trechos(trechos)]
    if evitar is not None:
        # A substituição reusa a MESMA âncora: sem esta instrução, a mesma
        # temperatura tenderia a devolver quase a mesma questão.
        partes.append(
            "Questão que está sendo substituída — não a repita. Escreva OUTRA "
            "questão: pergunte outra coisa sobre os trechos (outro aspecto, outra "
            "habilidade), e não a mesma pergunta com outras palavras.\n" + evitar
        )
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
) -> ResultadoGeracao:
    # O texto da âncora É a consulta: ela já decidiu o assunto, e o RAG só
    # traz o contexto vizinho.
    trechos = buscar(
        db,
        embeddings,
        reranker,
        sessao,
        ancora.texto,
        k=settings.rag_top_k,
        candidatos=settings.rag_candidatos,
    )

    sistema = montar_sistema(tipo, parametros_da_sessao(sessao, distribuicao))

    resposta = provedor.gerar(
        sessao.id,
        RequisicaoLLM(
            sistema=sistema,
            usuario=_montar_usuario(
                trechos, faixa, sessao.k_alternativas, tipo, evitar
            ),
            formato=montar_schema(tipo, sessao.k_alternativas),
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
