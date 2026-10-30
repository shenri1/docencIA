"""Compara o extrator nativo (PyMuPDF) com a saída do MinerU —.

O MinerU é rodado por fora, na versão fixada (veja o Quick Start dela):

    mineru -p material.pdf -o saida_mineru

e este script lê `saida_mineru/**/<nome>_content_list.json`. Nada aqui chama o
MinerU nem LLM. 

    uv run --project avaliacao python -m avaliacao.comparar_extratores \
        --mineru saida_mineru aula1.pdf aula2.pdf
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pymupdf

from avaliacao.extratores import metricas, paginas_do_content_list


def _nativo(pdf: Path) -> tuple[dict[int, str], float]:
    inicio = time.perf_counter()
    with pymupdf.open(pdf) as doc:
        paginas = {i: p.get_text("text").strip() for i, p in enumerate(doc, start=1)}
    return paginas, time.perf_counter() - inicio


def _mineru(pasta: Path, pdf: Path):
    achados = sorted(pasta.rglob(f"{pdf.stem}_content_list.json"))
    if not achados:
        return None
    return paginas_do_content_list(json.loads(achados[0].read_text(encoding="utf-8")))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--mineru", type=Path, required=True, help="pasta de saída do MinerU")
    args = ap.parse_args()

    print("| material | extrator | páginas | vazias | chars | linhas repetidas | chars repetidos | tabelas | fórmulas | s (nativo) |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for pdf in args.pdfs:
        paginas, segundos = _nativo(pdf)
        m = metricas(paginas)
        print(f"| {pdf.name} | nativo | {m['paginas']} | {m['paginas_vazias']} | {m['chars']} | {m['linhas_repetidas']} | {m['chars_repetidos']} | n/d | n/d | {segundos:.1f} |")
        lido = _mineru(args.mineru, pdf)
        if lido is None:
            print(f"| {pdf.name} | mineru | sem content_list.json em {args.mineru} | | | | | | | |")
            continue
        paginas_m, tipos = lido
        m = metricas(paginas_m)
        print(f"| {pdf.name} | mineru | {m['paginas']} | {m['paginas_vazias']} | {m['chars']} | {m['linhas_repetidas']} | {m['chars_repetidos']} | {tipos.get('table', 0)} | {tipos.get('equation', 0)} | medir à mão |")


if __name__ == "__main__":
    main()
