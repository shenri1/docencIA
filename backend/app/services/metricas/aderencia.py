"""Aderência da questão ao tema e aos trechos citados — Núcleo
Semântico, porque chama o juiz. Só observa: nada aqui levanta nem muda o aceite
da questão. O juiz recebe só o tema, a questão e os trechos citados (R2).
"""

from __future__ import annotations

from backend.app.domain import TipoQuestao
from backend.app.services.metricas.coletor import Coletor
from backend.app.services.metricas.juiz import FalhaJuizException, Juiz
from backend.app.services.rag.embeddings import Embeddings

_ERRO_MAX = 200


def tema_da_sessao(sessao) -> tuple[str, str]:
    if sessao.tema_escopo:
        return sessao.tema_escopo, "tema_escopo"
    return sessao.disciplina, "disciplina"


def texto_da_questao(questao) -> str:
    """Enunciado e alternativas (objetiva) ou aspectos esperados (discursiva).
    Sem a justificativa estruturada."""
    linhas = [questao.enunciado]
    if questao.tipo is TipoQuestao.OBJETIVA:
        linhas += [
            f"{a.letra}) {a.texto}"
            for a in sorted(questao.alternativas, key=lambda a: a.letra)
        ]
    else:
        linhas += [f"- {a.texto}" for a in questao.aspectos]
    return "\n".join(linhas)


def _texto_para_o_juiz(questao) -> str:
    """O juiz só mede se a resposta correta é sustentada se souber qual é."""
    texto = texto_da_questao(questao)
    if questao.tipo is TipoQuestao.OBJETIVA:
        corretas = sorted(a.letra for a in questao.alternativas if a.correta)
        texto += f"\nResposta correta: {', '.join(corretas)}"
    return texto


def _cosseno(a: list[float], b: list[float]) -> float:
    # Os vetores já saem normalizados do `Embeddings`, então o cosseno é o
    # produto escalar.
    return round(sum(x * y for x, y in zip(a, b, strict=True)), 4)


def _embedding(
    questao, tema: str, trechos: list[str], embeddings: Embeddings, coletor: Coletor
) -> dict:
    try:
        with coletor.medir("embedding_aderencia"):
            vetores = embeddings.embutir_documentos(
                [texto_da_questao(questao), tema, *trechos]
            )
        q, t, *citados = vetores
        return {
            "cos_tema": _cosseno(q, t),
            "cos_trecho_max": max((_cosseno(q, c) for c in citados), default=None),
        }
    except Exception as exc:  # noqa: BLE001  # observador: nada aqui pode derrubar a geração
        return {"erro": str(exc)[:_ERRO_MAX]}


def _juiz(
    questao, tema: str, trechos: list[str], juiz: Juiz | None, coletor: Coletor
) -> dict:
    if juiz is None:
        return {"erro": "juiz não configurado"}
    try:
        with coletor.medir("juiz"):
            r = juiz.avaliar(tema, _texto_para_o_juiz(questao), trechos)
    except FalhaJuizException as exc:
        return {"erro": str(exc)[:_ERRO_MAX]}
    coletor.anotar_tokens("juiz", r.uso, r.modelo)
    return {
        "nota_tema": r.avaliacao.nota_tema,
        "nota_trecho": r.avaliacao.nota_trecho,
        "justificativa": r.avaliacao.justificativa,
        "modelo": r.modelo,
        "versao_prompt": r.versao_prompt,
    }


def medir_aderencia(
    questao,
    sessao,
    trechos_citados: list[str],
    embeddings: Embeddings,
    juiz: Juiz | None,
    coletor: Coletor,
) -> dict:
    """Nunca levanta."""
    tema, origem = tema_da_sessao(sessao)
    return {
        "tema": {"origem": origem, "texto": tema},
        "embedding": _embedding(questao, tema, trechos_citados, embeddings, coletor),
        "juiz": _juiz(questao, tema, trechos_citados, juiz, coletor),
    }
