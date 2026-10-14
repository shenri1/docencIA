"""Gera o DOCX para abrir no Word e no LibreOffice.

Fora da suíte normal: só roda com GERAR_DOCX_VERIFICACAO=<caminho do arquivo>.
A suíte não tem Word, e um OMML malformado só aparece abrindo o arquivo.
"""

import os
from pathlib import Path

import pytest

from backend.app.services.exportacao.renderizacao import renderizar_conteudo_puro
from backend.tests.services.exportacao.test_renderizacao import (
    CABECALHO,
    objetiva,
    prova,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("GERAR_DOCX_VERIFICACAO"),
    reason="gera arquivo para abrir no Word",
)

# Uma questão por construção do subconjunto.
CONSTRUCOES = [
    r"Potência: \(x^2\) e índice \(x_1\).",
    r"Fração: \(\frac{a}{b}\).",
    r"Raiz: \(\sqrt{x}\) e \(\sqrt[3]{x}\).",
    r"Somatório: \(\sum_{i=1}^{n} i\).",
    r"Integral: \(\int_0^1 x^2 dx\).",
    r"Produtório: \(\prod_{k=1}^{n} k\).",
    r"Limite: \(\lim_{x \to 0} f(x)\).",
    r"Gregas: \(\alpha + \beta + \Omega\).",
    r"Química: \(\mathrm{H_2SO_4}\) e \(\mathrm{N_2 + 3H_2 \rightleftharpoons 2NH_3}\).",
    r"Relações: \(a \leq b \neq c \approx d \pm e\).",
    r"Delimitadores: \(\left( \frac{a}{b} \right)\).",
    r"Matriz: \(\begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}\).",
    "Em destaque:\n\\[\\int_0^1 \\frac{x}{2} dx\\]\nDepois da fórmula.",
    r"Inválida, deve sair crua: \(\color{red}{x}\).",
]


def test_gera_docx_de_verificacao():
    itens = [
        objetiva(i, texto, ["a", "b", "c", "d", "e"])
        for i, texto in enumerate(CONSTRUCOES, 1)
    ]
    dados = renderizar_conteudo_puro(CABECALHO, prova("A", itens), prova("B", itens))
    Path(os.environ["GERAR_DOCX_VERIFICACAO"]).write_bytes(dados)
