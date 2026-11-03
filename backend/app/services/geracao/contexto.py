"""O que Gerador e Crítico precisam ver igual — Núcleo Determinístico.

Formatação dos trechos, parâmetros de montagem do prompt e resolução de
fontes. Extraído do Gerador para que o crítico veja o material exatamente como
o Gerador viu, e para que só a versão revisada tenha as fontes resolvidas.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from backend.app.exceptions import FonteInvalidaException, FonteNaoSustentadaException
from backend.app.models.identidade import SessaoGeracao
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services.calculo_distribuicao_service import DistribuicaoQuestoes
from backend.app.services.metricas.sustentacao import normalizar, sustenta
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


def _palavras_da_localizacao(localizacao: str) -> set[str]:
    return set(re.findall(r"\w+", normalizar(localizacao)))


def _localizacao_confere(informada: str, do_chunk: str) -> bool:
    """O chunk pode juntar várias localizações ("página 12; página 13"). A do
    modelo confere se coincide com uma delas ou a detalha ("página 12,
    parágrafo 3"). Compara palavras inteiras: "página 1" não casa com
    "página 12"."""
    dela = _palavras_da_localizacao(informada)
    if not dela:
        return False
    for parte in do_chunk.split(";"):
        da_parte = _palavras_da_localizacao(parte)
        if da_parte and (dela <= da_parte or da_parte <= dela):
            return True
    return False


def resolver_fontes(
    fontes, trechos: list[TrechoRecuperado]
) -> list[tuple[int, str, str]]:
    """O modelo devolve o identificador como texto ("P1"). Resolver contra os
    trechos efetivamente enviados é o que impede de virar ficção.

    Não basta o identificador existir: o `trecho_base` tem de constar num chunk
    daquele material, senão a questão não é gerada (regra da fonte) em vez de
    ser gravada com uma citação que o docente não consegue conferir.

    A `localizacao` do modelo é só mantida se confere com a do chunk que contém
    o trecho. Se não conferir (ele erra página com facilidade), vale a do chunk:
    o trecho é real, então a questão é boa e a fonte gravada passa a ser
    verdadeira, em vez de descartar a questão por um metadado."""
    por_identificador = {t.identificador_curto: t.material_id for t in trechos}
    resolvidas: list[tuple[int, str, str]] = []
    for fonte in fontes:
        material_id = por_identificador.get(fonte.identificador_material)
        if material_id is None:
            raise FonteInvalidaException(
                fonte.identificador_material, sorted(por_identificador)
            )
        sustentam = [
            t
            for t in trechos
            if t.material_id == material_id and sustenta(fonte.trecho_base, t)
        ]
        if not sustentam:
            raise FonteNaoSustentadaException(
                fonte.identificador_material, fonte.trecho_base
            )
        localizacao = fonte.localizacao
        if not any(_localizacao_confere(localizacao, t.localizacao) for t in sustentam):
            localizacao = sustentam[0].localizacao
        resolvidas.append((material_id, localizacao, fonte.trecho_base))
    return resolvidas
