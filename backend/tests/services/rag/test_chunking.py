from backend.app.domain import OrigemTexto
from backend.app.services.extracao.tipos import BlocoTexto
from backend.app.services.rag.chunking import (
    ConfigChunking,
    combinar_localizacoes,
    dividir_em_chunks,
)

CFG = ConfigChunking(max_chars=1200, overlap_chars=200, min_chars=300)


def bloco(localizacao: str, texto: str) -> BlocoTexto:
    return BlocoTexto(localizacao=localizacao, texto=texto, origem=OrigemTexto.NATIVO)


def test_bloco_de_tamanho_normal_vira_um_chunk():
    blocos = [bloco("página 1", "a" * 500)]
    chunks = dividir_em_chunks(blocos, CFG)
    assert len(chunks) == 1
    assert chunks[0].localizacao == "página 1"
    assert chunks[0].ordem == 0


def test_blocos_curtos_sao_unidos_ate_o_minimo():
    blocos = [bloco(f"página {n}", "palavra " * 15) for n in (1, 2, 3)]
    chunks = dividir_em_chunks(blocos, CFG)
    assert len(chunks) == 1
    assert chunks[0].localizacao == "páginas 1–3"


def test_bloco_longo_e_partido_com_sobreposicao():
    texto = " ".join(f"palavra{n}" for n in range(400))
    chunks = dividir_em_chunks([bloco("página 7", texto)], CFG)
    assert len(chunks) > 1
    assert all(len(c.texto) <= CFG.max_chars for c in chunks)
    # Sobreposição: o fim do primeiro chunk reaparece no começo do segundo.
    cauda = chunks[0].texto[-50:]
    assert cauda in chunks[1].texto
    # Localização do bloco de origem é preservada em cada pedaço.
    assert {c.localizacao for c in chunks} == {"página 7"}


def test_ordem_e_sequencial_comecando_em_zero():
    blocos = [bloco(f"slide {n}", "conteúdo " * 60) for n in range(1, 4)]
    chunks = dividir_em_chunks(blocos, CFG)
    assert [c.ordem for c in chunks] == list(range(len(chunks)))


def test_blocos_vazios_sao_ignorados():
    blocos = [bloco("página 1", "   "), bloco("página 2", "x" * 400)]
    chunks = dividir_em_chunks(blocos, CFG)
    assert len(chunks) == 1
    assert chunks[0].localizacao == "página 2"


def test_chunking_e_deterministico():
    blocos = [bloco(f"página {n}", f"texto {n} " * 80) for n in range(1, 6)]
    assert dividir_em_chunks(blocos, CFG) == dividir_em_chunks(blocos, CFG)


def test_combinar_uma_localizacao_devolve_ela_mesma():
    assert combinar_localizacoes(["página 3"]) == "página 3"


def test_combinar_paginas_contiguas_vira_intervalo():
    assert combinar_localizacoes(["página 3", "página 4"]) == "páginas 3–4"


def test_combinar_slides_contiguos_vira_intervalo():
    assert combinar_localizacoes(["slide 2", "slide 3"]) == "slides 2–3"


def test_combinar_paragrafos_com_secao_preserva_a_secao():
    entrada = ["Introdução · par. 3", "Introdução · par. 4"]
    assert combinar_localizacoes(entrada) == "Introdução · par. 3–4"


def test_combinar_linhas_usa_os_extremos():
    assert combinar_localizacoes(["linhas 1–4", "linhas 6–9"]) == "linhas 1–9"


def test_combinar_paginas_nao_contiguas_junta_com_ponto_e_virgula():
    assert combinar_localizacoes(["página 3", "página 7"]) == "página 3; página 7"


def test_combinar_unidades_diferentes_junta_com_ponto_e_virgula():
    assert combinar_localizacoes(["página 3", "slide 4"]) == "página 3; slide 4"


def test_combinar_secoes_diferentes_junta_com_ponto_e_virgula():
    entrada = ["Introdução · par. 3", "Métodos · par. 4"]
    assert combinar_localizacoes(entrada) == "Introdução · par. 3; Métodos · par. 4"


def test_combinar_formato_desconhecido_nao_explode():
    assert combinar_localizacoes(["algo estranho", "página 2"]) == (
        "algo estranho; página 2"
    )
