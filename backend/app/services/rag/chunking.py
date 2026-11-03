"""Chunking de material — Núcleo Determinístico, nunca chama LLM.

Função pura: sem I/O, sem rede. Os mesmos blocos produzem sempre os mesmos
chunks, e é isso que permite testar esta camada sem banco e sem modelo.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from backend.app.core.config import settings
from backend.app.models.materiais import TAMANHO_LOCALIZACAO
from backend.app.services.extracao.tipos import BlocoTexto


@dataclass(frozen=True)
class Chunk:
    texto: str
    localizacao: str
    ordem: int


@dataclass(frozen=True)
class ConfigChunking:
    max_chars: int
    overlap_chars: int
    min_chars: int

    @classmethod
    def das_settings(cls) -> ConfigChunking:
        return cls(
            max_chars=settings.chunk_max_chars,
            overlap_chars=settings.chunk_overlap_chars,
            min_chars=settings.chunk_min_chars,
        )


# Os cinco formatos que emite, mais o prefixo de seção do DOCX.
_NUMERADA = re.compile(
    r"^(?:(?P<secao>.+?) · )?(?P<unidade>página|slide|par\.|tabela) (?P<numero>\d+)$"
)
_LINHAS = re.compile(r"^linhas (?P<inicio>\d+)–(?P<fim>\d+)$")
_PLURAL = {
    "página": "páginas",
    "slide": "slides",
    "tabela": "tabelas",
    "par.": "par.",
}


def _abreviar(texto: str, limite: int) -> str:
    if len(texto) <= limite:
        return texto
    return texto[: limite - 1].rstrip() + "…"


def combinar_localizacoes(localizacoes: list[str]) -> str:
    """Une localizações de blocos adjacentes num intervalo legível.

    Só vira intervalo quando seção e unidade são as mesmas e a numeração é
    contígua. Qualquer outro caso junta com "; " — inclusive formato
    desconhecido, para que a função nunca falhe por localização inesperada.

    O resultado nunca passa de `TAMANHO_LOCALIZACAO`: o título de seção do DOCX
    entra inteiro na localização, então a junção (ou até uma só) pode estourar
    a coluna. Passando do teto, a junção vira "primeira … última", cada ponta
    abreviada se preciso.
    """
    combinada = _combinar(localizacoes)
    if len(combinada) <= TAMANHO_LOCALIZACAO:
        return combinada
    if len(localizacoes) == 1:
        return _abreviar(combinada, TAMANHO_LOCALIZACAO)
    meio = (TAMANHO_LOCALIZACAO - len(" … ")) // 2
    return f"{_abreviar(localizacoes[0], meio)} … {_abreviar(localizacoes[-1], meio)}"


def _combinar(localizacoes: list[str]) -> str:
    if len(localizacoes) == 1:
        return localizacoes[0]

    faixas = [_LINHAS.match(loc) for loc in localizacoes]
    if all(faixas):
        inicio = min(int(m["inicio"]) for m in faixas)
        fim = max(int(m["fim"]) for m in faixas)
        return f"linhas {inicio}–{fim}"

    casados = [_NUMERADA.match(loc) for loc in localizacoes]
    if all(casados):
        secoes = {m["secao"] for m in casados}
        unidades = {m["unidade"] for m in casados}
        numeros = [int(m["numero"]) for m in casados]
        contiguo = numeros == list(range(numeros[0], numeros[0] + len(numeros)))
        if len(secoes) == 1 and len(unidades) == 1 and contiguo:
            faixa = f"{_PLURAL[unidades.pop()]} {numeros[0]}–{numeros[-1]}"
            secao = secoes.pop()
            return f"{secao} · {faixa}" if secao else faixa

    return "; ".join(localizacoes)


def _fronteira(texto: str, fim: int, max_chars: int) -> int:
    """Procura a última fronteira de palavra nos últimos 15% da janela."""
    margem = max(1, int(max_chars * 0.15))
    janela = texto[fim - margem : fim]
    posicao = max(janela.rfind(" "), janela.rfind("\n"))
    if posicao == -1:
        return fim
    return fim - margem + posicao + 1


def _partir(texto: str, cfg: ConfigChunking) -> list[str]:
    pedacos: list[str] = []
    inicio = 0
    while inicio < len(texto):
        fim = inicio + cfg.max_chars
        if fim >= len(texto):
            pedacos.append(texto[inicio:])
            break
        corte = _fronteira(texto, fim, cfg.max_chars)
        pedacos.append(texto[inicio:corte])
        # max() garante progresso mesmo se a sobreposição for grande demais.
        inicio = max(corte - cfg.overlap_chars, inicio + 1)
    return [p for p in (pedaco.strip() for pedaco in pedacos) if p]


def dividir_em_chunks(blocos: Sequence[BlocoTexto], cfg: ConfigChunking) -> list[Chunk]:
    brutos: list[tuple[str, list[str]]] = []
    acumulado: list[str] = []
    localizacoes: list[str] = []

    def fechar() -> None:
        if acumulado:
            brutos.append(("\n".join(acumulado), list(localizacoes)))
            acumulado.clear()
            localizacoes.clear()

    for bloco in blocos:
        texto = bloco.texto.strip()
        if not texto:
            continue
        if len(texto) > cfg.max_chars:
            fechar()
            for pedaco in _partir(texto, cfg):
                brutos.append((pedaco, [bloco.localizacao]))
            continue
        if acumulado and sum(map(len, acumulado)) + len(texto) > cfg.max_chars:
            fechar()
        acumulado.append(texto)
        localizacoes.append(bloco.localizacao)
        if sum(map(len, acumulado)) >= cfg.min_chars:
            fechar()
    fechar()

    return [
        Chunk(texto=texto, localizacao=combinar_localizacoes(locs), ordem=ordem)
        for ordem, (texto, locs) in enumerate(brutos)
    ]
