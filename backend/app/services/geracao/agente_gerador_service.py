"""Agente Gerador — Núcleo Semântico.

Gera UMA questão a partir de uma âncora. O laço do banco é do banco_service:
aqui não há iteração, persistência nem transação.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.domain import FaixaDificuldade
from backend.app.exceptions import FonteInvalidaException
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.materiais import ChunkMaterial
from backend.app.prompt.montagem import montar_sistema
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.schemas.geracao import InsuficienciaFonte, montar_schema_questao
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.provedor.tipos import RequisicaoLLM
from backend.app.services.rag.retrieval_service import TrechoRecuperado, buscar


@dataclass(frozen=True)
class ResultadoGeracao:
    numero: int
    questao: object | None
    motivo_insuficiencia: str | None
    localizacao_ancora: str
    # (material_id, localizacao, trecho_base) — já resolvido contra os trechos
    # enviados, pronto para virar FonteInterna.
    fontes_resolvidas: list[tuple[int, str, str]]


def _montar_usuario(
    trechos: list[TrechoRecuperado], faixa: FaixaDificuldade, k: int
) -> str:
    linhas = [f"[{t.identificador_curto}, {t.localizacao}] {t.texto}" for t in trechos]
    return (
        "Trechos disponíveis:\n"
        + "\n\n".join(linhas)
        + f"\n\nGere UMA questão de dificuldade {faixa.value} com exatamente "
        f"{k} alternativas, usando apenas os trechos acima."
    )


def _resolver_fontes(
    fontes, trechos: list[TrechoRecuperado]
) -> list[tuple[int, str, str]]:
    """O modelo devolve o identificador como texto ("P1"). Resolver contra os
    trechos efetivamente enviados é o que impede de virar ficção."""
    por_identificador = {t.identificador_curto: t.material_id for t in trechos}
    resolvidas: list[tuple[int, str, str]] = []
    for fonte in fontes:
        material_id = por_identificador.get(fonte.identificador_material)
        if material_id is None:
            raise FonteInvalidaException(
                fonte.identificador_material, sorted(por_identificador)
            )
        resolvidas.append((material_id, fonte.localizacao, fonte.trecho_base))
    return resolvidas


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

    sistema = montar_sistema(
        ParametrosGeracao(
            disciplina=sessao.disciplina,
            periodo=sessao.periodo,
            area_do_conhecimento=sessao.area_do_conhecimento,
            tema_escopo=sessao.tema_escopo,
            k_alternativas=sessao.k_alternativas,
            n_faceis=distribuicao.faceis,
            n_medias=distribuicao.medias,
            n_dificeis=distribuicao.dificeis,
        )
    )

    resposta = provedor.gerar(
        sessao.id,
        RequisicaoLLM(
            sistema=sistema,
            usuario=_montar_usuario(trechos, faixa, sessao.k_alternativas),
            formato=montar_schema_questao(sessao.k_alternativas),
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
            fontes_resolvidas=[],
        )

    return ResultadoGeracao(
        numero=numero,
        questao=conteudo,
        motivo_insuficiencia=None,
        localizacao_ancora=ancora.localizacao,
        fontes_resolvidas=_resolver_fontes(conteudo.fontes, trechos),
    )
