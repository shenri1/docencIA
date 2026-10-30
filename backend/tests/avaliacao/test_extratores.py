"""Métricas da comparação de extratores — puras, sobre texto por página."""

from avaliacao.extratores import (
    linhas_repetidas,
    metricas,
    paginas_do_content_list,
)


def test_content_list_vira_texto_por_pagina_com_numeracao_a_partir_de_1():
    itens = [
        {"type": "text", "text": "Título", "page_idx": 0},
        {"type": "text", "text": "Corpo", "page_idx": 0},
        {"type": "table", "table_body": "<table>x</table>", "page_idx": 1},
        {"type": "equation", "text": "$$E=mc^2$$", "page_idx": 1},
        {"type": "image", "img_path": "a.png", "page_idx": 1},
    ]

    paginas, contagem = paginas_do_content_list(itens)

    assert paginas == {1: "Título\nCorpo", 2: "<table>x</table>\n$$E=mc^2$$"}
    assert contagem == {"text": 2, "table": 1, "equation": 1, "image": 1}


def test_linha_em_metade_ou_mais_das_paginas_conta_como_cabecalho_repetido():
    paginas = {
        1: "Curso de Física\nconteúdo um\n1",
        2: "Curso de Física\nconteúdo dois\n2",
        3: "Curso de Física\nconteúdo três\n3",
        4: "outro assunto",
    }

    assert linhas_repetidas(paginas) == ["Curso de Física"]


def test_poucas_paginas_nao_acusam_repeticao():
    assert linhas_repetidas({1: "igual", 2: "igual"}) == []


def test_metricas_somam_caracteres_e_contam_paginas_vazias_e_repetidas():
    paginas = {
        1: "Cabeçalho X\nabc",
        2: "Cabeçalho X\ndef",
        3: "Cabeçalho X\n",
        4: "",
    }

    m = metricas(paginas)

    assert m["paginas"] == 4
    assert m["paginas_vazias"] == 1
    assert m["linhas_repetidas"] == 1
    assert m["chars_repetidos"] == 3 * len("Cabeçalho X")
    assert m["chars"] == sum(len(t) for t in paginas.values())
