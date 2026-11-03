from backend.app.domain import OrigemTexto
from backend.app.models.materiais import TAMANHO_LOCALIZACAO, ChunkMaterial
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


TITULO_LONGO = "Fundamentos teóricos e metodológicos da análise de algoritmos em grafos"


def test_limite_e_o_tamanho_da_coluna():
    """Se a coluna mudar, o teto do chunking acompanha: um valor só."""
    coluna = ChunkMaterial.__table__.columns["localizacao"]
    assert TAMANHO_LOCALIZACAO == coluna.type.length == 255


def test_combinar_secoes_longas_resume_pelas_pontas():
    entrada = [f"{TITULO_LONGO} {n} · par. {n}" for n in (1, 2, 3, 4)]
    combinada = combinar_localizacoes(entrada)
    assert len(combinada) <= TAMANHO_LOCALIZACAO
    assert combinada.startswith(TITULO_LONGO + " 1")
    assert combinada.endswith("par. 4")
    assert " … " in combinada


def test_combinar_que_cabe_continua_com_ponto_e_virgula():
    entrada = ["Introdução · par. 3", "Métodos · par. 4", "Resultados · par. 5"]
    assert combinar_localizacoes(entrada) == (
        "Introdução · par. 3; Métodos · par. 4; Resultados · par. 5"
    )


def test_combinar_extremos_longos_sao_abreviados_e_cabem():
    entrada = ["A" * 400 + " · par. 1", "B" * 400 + " · par. 9"]
    combinada = combinar_localizacoes(entrada)
    assert len(combinada) <= TAMANHO_LOCALIZACAO
    assert combinada.startswith("A") and "…" in combinada
    assert combinada.rstrip().endswith("…")


def test_localizacao_unica_longa_e_abreviada():
    """Título de seção do DOCX com 400 caracteres: nem precisa combinar."""
    combinada = combinar_localizacoes(["T" * 400 + " · par. 1"])
    assert len(combinada) == TAMANHO_LOCALIZACAO
    assert combinada.endswith("…")


def test_chunks_nunca_passam_do_limite_da_coluna():
    blocos = [
        bloco(f"{TITULO_LONGO} {n} · par. {n}", "palavra " * 15)
        for n in range(1, 40, 2)
    ]
    blocos.append(bloco("T" * 500 + " · par. 99", "x" * 1500))
    chunks = dividir_em_chunks(blocos, CFG)
    assert len(chunks) > 1
    assert all(len(c.localizacao) <= TAMANHO_LOCALIZACAO for c in chunks)


def test_combinar_formato_desconhecido_nao_explode():
    assert combinar_localizacoes(["algo estranho", "página 2"]) == (
        "algo estranho; página 2"
    )
