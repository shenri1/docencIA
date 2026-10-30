"""Métricas para comparar extratores de PDF — puro, sem MinerU nem PyMuPDF.

Tudo parte de `{página: texto}`. O MinerU entra pela saída `content_list.json`
dele (confira os nomes dos campos na versão que instalar).
"""

from __future__ import annotations

from collections import Counter

MIN_PAGINAS_PARA_REPETICAO = 3


def paginas_do_content_list(itens: list[dict]) -> tuple[dict[int, str], dict[str, int]]:
    """Blocos do MinerU → texto por página (1-based) e contagem por tipo."""
    por_pagina: dict[int, list[str]] = {}
    tipos: Counter[str] = Counter()
    for item in itens:
        tipos[item["type"]] += 1
        texto = item.get("text") or item.get("table_body") or ""
        if texto:
            por_pagina.setdefault(item["page_idx"] + 1, []).append(texto)
    return {p: "\n".join(t) for p, t in sorted(por_pagina.items())}, dict(tipos)


def linhas_repetidas(paginas: dict[int, str]) -> list[str]:
    """Linhas presentes em metade ou mais das páginas: cabeçalho e rodapé que
    vão parar em todo chunk."""
    if len(paginas) < MIN_PAGINAS_PARA_REPETICAO:
        return []
    por_linha: Counter[str] = Counter()
    for texto in paginas.values():
        por_linha.update({l.strip() for l in texto.splitlines() if l.strip()})
    minimo = max(MIN_PAGINAS_PARA_REPETICAO, len(paginas) / 2)
    return sorted(l for l, n in por_linha.items() if n >= minimo)


def metricas(paginas: dict[int, str]) -> dict[str, int]:
    repetidas = linhas_repetidas(paginas)
    chars_repetidos = sum(
        len(linha)
        for texto in paginas.values()
        for linha in {l.strip() for l in texto.splitlines()}
        if linha in repetidas
    )
    return {
        "paginas": len(paginas),
        "paginas_vazias": sum(not t.strip() for t in paginas.values()),
        "chars": sum(len(t) for t in paginas.values()),
        "linhas_repetidas": len(repetidas),
        "chars_repetidos": chars_repetidos,
    }
