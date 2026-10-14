"""O que Gerador e Crítico precisam ver igual — Núcleo Determinístico.

Formatação dos trechos, parâmetros de montagem do prompt e resolução de
fontes. Extraído do Gerador para que o crítico veja o material exatamente como
o Gerador viu, e para que só a versão revisada tenha as fontes resolvidas.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.exceptions import FonteInvalidaException
from backend.app.models.identidade import SessaoGeracao
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.rag.retrieval_service import TrechoRecuperado


def formatar_trechos(trechos: list[TrechoRecuperado]) -> str:
    return "\n\n".join(
        f"[{t.identificador_curto}, {t.localizacao}] {t.texto}" for t in trechos
    )


def formatar_orientacoes(orientacoes: Sequence) -> str | None:
    """Gerador e Crítico recebem o mesmo bloco. Nada aqui interpreta o
    texto: é numeração e concatenação."""
    if not orientacoes:
        return None
    linhas = []
    for numero, orientacao in enumerate(orientacoes, start=1):
        partes = []
        if orientacao.cruzar_com:
            partes.append(f"Articular com: {orientacao.cruzar_com}")
        if orientacao.o_que_mudar:
            partes.append(f"Mudar: {orientacao.o_que_mudar}")
        linhas.append(f"{numero}. " + ". ".join(partes))
    return "Orientações do docente:\n" + "\n".join(linhas)


def parametros_da_sessao(
    sessao: SessaoGeracao, distribuicao: DistribuicaoQuestoes
) -> ParametrosGeracao:
    return ParametrosGeracao(
        disciplina=sessao.disciplina,
        periodo=sessao.periodo,
        area_do_conhecimento=sessao.area_do_conhecimento,
        tema_escopo=sessao.tema_escopo,
        k_alternativas=sessao.k_alternativas,
        n_faceis=distribuicao.faceis,
        n_medias=distribuicao.medias,
        n_dificeis=distribuicao.dificeis,
    )


def resolver_fontes(
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
