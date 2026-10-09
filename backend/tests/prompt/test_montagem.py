import pytest

from backend.app.domain import TipoQuestao
from backend.app.exceptions import PlaceholderNaoResolvidoException
from backend.app.prompt import montagem
from backend.app.prompt.montagem import (
    calcular_hash,
    carregar_modulos,
    carregar_modulos_versionados,
    montar_sistema,
    montar_sistema_auditor,
    montar_sistema_critico,
)
from backend.app.prompt.parametros import ParametrosGeracao

OBJ = TipoQuestao.OBJETIVA
DISC = TipoQuestao.DISCURSIVA


def params(**sobrescritas) -> ParametrosGeracao:
    base = {
        "disciplina": "Algoritmos",
        "periodo": "2026.2",
        "area_do_conhecimento": "Computação",
        "tema_escopo": "Grafos",
        "k_alternativas": 5,
        "n_faceis": 5,
        "n_medias": 30,
        "n_dificeis": 15,
    }
    base.update(sobrescritas)
    return ParametrosGeracao(**base)


def test_modulos_por_pasta_em_ordem():
    for pasta in ("comum", "objetiva", "discursiva"):
        nomes = [n for n, _ in carregar_modulos(pasta)]
        assert nomes == sorted(nomes)
        assert all(n.startswith(f"{pasta}/") for n in nomes)


def test_objetiva_injeta_placeholders():
    texto = montar_sistema(OBJ, params())
    for esperado in ("Algoritmos", "2026.2", "Computação", "Grafos"):
        assert esperado in texto
    assert "exatamente 5 alternativas" in texto
    assert "30 médias" in texto
    assert "{{" not in texto


def test_discursiva_nao_fala_de_alternativas():
    texto = montar_sistema(DISC, params())
    assert "<formato_discursiva>" in texto
    assert "<qualidade_alternativas>" not in texto
    assert "exatamente 5 alternativas" not in texto
    assert "letra_correta" not in texto
    assert "{{" not in texto


def test_objetiva_nao_leva_modulos_da_discursiva():
    texto = montar_sistema(OBJ, params())
    assert "<formato_discursiva>" not in texto
    assert "<revisor>" not in texto


def test_os_dois_tipos_compartilham_identidade_e_fontes():
    for tipo in (OBJ, DISC):
        texto = montar_sistema(tipo, params())
        assert "<identidade>" in texto
        assert "<politica_fontes>" in texto


@pytest.mark.parametrize("tipo", [OBJ, DISC])
def test_critico_de_cada_tipo(tipo):
    texto = montar_sistema_critico(tipo, params())
    assert texto.index("<revisor>") < texto.index("<politica_fontes>")
    assert "<identidade>" not in texto
    assert "<exemplos>" not in texto
    assert "{{" not in texto
    if tipo is OBJ:
        assert "<revisao_objetiva>" in texto
        assert "<qualidade_alternativas>" in texto
        assert "<revisao_discursiva>" not in texto
    else:
        assert "<revisao_discursiva>" in texto
        assert "<formato_discursiva>" in texto
        assert "<qualidade_alternativas>" not in texto


def test_placeholder_faltando_levanta_excecao(tmp_path, monkeypatch):
    (tmp_path / "comum").mkdir()
    (tmp_path / "objetiva").mkdir()
    (tmp_path / "comum" / "01_teste.md").write_text(
        "Disciplina: {{disciplina}} e {{inexistente}}"
    )
    monkeypatch.setattr(montagem, "DIRETORIO_MODULOS", tmp_path)
    with pytest.raises(PlaceholderNaoResolvidoException, match="inexistente"):
        montar_sistema(OBJ, params())


def test_campos_opcionais_nulos_viram_texto_legivel():
    texto = montar_sistema(OBJ, params(area_do_conhecimento=None, tema_escopo=None))
    assert "{{" not in texto
    assert "não informada" in texto or "não informado" in texto


def test_prompt_montado_nao_tem_vocabulario_medico():
    for tipo in (OBJ, DISC):
        texto = montar_sistema(tipo, params()).lower()
        for proibido in ("medicina", "fisiopatológico", "clínico", "livro oficial"):
            assert proibido not in texto


@pytest.mark.parametrize("k", [2, 5, 11])
def test_k_nas_pontas_da_faixa_permitida(k):
    assert f"exatamente {k} alternativas" in montar_sistema(OBJ, params(k_alternativas=k))


def test_regra_1_usa_media_das_demais():
    texto = montar_sistema(OBJ, params())
    assert "média de palavras das demais alternativas" in texto


def test_versionados_cobrem_todas_as_pastas_com_caminho_relativo():
    nomes = [n for n, _ in carregar_modulos_versionados()]
    assert nomes == sorted(nomes)
    for pasta in ("comum/", "objetiva/", "discursiva/", "critico/"):
        assert any(n.startswith(pasta) for n in nomes)
    # Nenhum módulo solto na raiz: a raiz só tem código.
    assert all("/" in n for n in nomes)


def test_hash_e_sensivel_ao_conteudo():
    modulos = carregar_modulos_versionados()
    alterado = [(modulos[0][0], modulos[0][1] + "x"), *modulos[1:]]
    assert calcular_hash(alterado) != calcular_hash(modulos)


def test_mover_modulo_entre_pastas_muda_o_hash():
    assert calcular_hash([("objetiva/x.md", "a")]) != calcular_hash(
        [("discursiva/x.md", "a")]
    )


def test_modulo_novo_em_pasta_entra_no_hash_e_no_tipo(tmp_path, monkeypatch):
    """Review Focus 5: rglob pega o arquivo sem ninguém precisar listá-lo."""
    for pasta in ("comum", "objetiva", "discursiva", "critico"):
        (tmp_path / pasta).mkdir()
    (tmp_path / "comum" / "01_a.md").write_text("A")
    (tmp_path / "discursiva" / "01_b.md").write_text("B")
    monkeypatch.setattr(montagem, "DIRETORIO_MODULOS", tmp_path)
    antes = calcular_hash(carregar_modulos_versionados())

    (tmp_path / "discursiva" / "04_extra.md").write_text("EXTRA")
    assert calcular_hash(carregar_modulos_versionados()) != antes
    assert "EXTRA" in montar_sistema(DISC, params())


def _modulo(pasta: str, nome: str) -> str:
    return (montagem.DIRETORIO_MODULOS / pasta / nome).read_text(encoding="utf-8")


def test_sistema_auditor_tem_auditor_qualidade_e_fontes():
    texto = montar_sistema_auditor(params())
    assert texto.index("<auditor>") < texto.index("<politica_fontes>")
    assert "<qualidade_alternativas>" in texto
    assert "{{" not in texto


def test_sistema_auditor_nao_tem_identidade_do_gerador_nem_exemplos():
    texto = montar_sistema_auditor(params())
    assert "<identidade>" not in texto
    assert "<exemplos>" not in texto


def test_sistema_do_gerador_nao_contem_texto_do_auditor():
    auditor = _modulo("auditor", "01_auditor.md")
    montado = montar_sistema(OBJ, params())
    assert auditor.strip()[:60] not in montado
    assert "<auditor>" not in montado


def test_modulo_do_auditor_entra_no_hash_de_versao():
    """`carregar_modulos_versionados` usa rglob, então a pasta nova entra no
    hash sem ninguém listá-la."""
    nomes = [nome for nome, _ in carregar_modulos_versionados()]
    assert "auditor/01_auditor.md" in nomes


def _classificacao() -> str:
    return (montagem.DIRETORIO_MODULOS / "comum" / "03_classificacao.md").read_text(
        encoding="utf-8"
    ).strip()[:60]


def test_classificacao_vai_para_o_gerador_dos_dois_tipos():
    """`carregar_modulos("comum")` varre a pasta, então o módulo novo entra sem
    ninguém listá-lo."""
    marca = _classificacao()
    assert marca in montar_sistema(OBJ, params())
    assert marca in montar_sistema(DISC, params())


def test_classificacao_vai_para_o_critico_dos_dois_tipos():
    """O crítico reemite a questão inteira, logo reemite `subtema`."""
    marca = _classificacao()
    assert marca in montar_sistema_critico(OBJ, params())
    assert marca in montar_sistema_critico(DISC, params())


def test_classificacao_nao_vai_para_o_auditor():
    """O auditor não emite questão: `subtema` não é assunto dele."""
    assert _classificacao() not in montar_sistema_auditor(params())


INSTRUCAO_LETRA = "nunca cite letra de alternativa"


def test_instrucao_de_letra_vai_para_gerador_e_critico_da_objetiva():
    assert INSTRUCAO_LETRA in montar_sistema(TipoQuestao.OBJETIVA, params()).lower()
    assert (
        INSTRUCAO_LETRA in montar_sistema_critico(OBJ, params()).lower()
    )


def test_instrucao_de_letra_nao_vai_para_o_auditor():
    """A proposta_ajuste do auditor cita letra DE PROPÓSITO."""
    assert INSTRUCAO_LETRA not in montar_sistema_auditor(params()).lower()

from backend.app.domain import FormatoItem  # noqa: E402

MARCAS_FORMATO = {
    FormatoItem.PROPOSICAO: "<formato_proposicao>",
    FormatoItem.AFIRMATIVAS: "<formato_afirmativas>",
    FormatoItem.ASSERCAO_RAZAO: "<formato_assercao_razao>",
}


@pytest.mark.parametrize("formato", list(FormatoItem))
def test_gerador_leva_so_o_modulo_do_formato(formato):
    texto = montar_sistema(OBJ, params(), formato)
    for outro, marca in MARCAS_FORMATO.items():
        assert (marca in texto) is (outro is formato)


# Crítico e auditor recebem o módulo de qualidade do formato: na proposição é o
# `02_qualidade_alternativas.md`; nos montados, o próprio `01_formato.md`.
MARCAS_QUALIDADE = {
    FormatoItem.PROPOSICAO: "<qualidade_alternativas>",
    FormatoItem.AFIRMATIVAS: "<formato_afirmativas>",
    FormatoItem.ASSERCAO_RAZAO: "<formato_assercao_razao>",
}


@pytest.mark.parametrize("formato", list(FormatoItem))
def test_critico_e_auditor_levam_o_modulo_do_formato(formato):
    assert MARCAS_QUALIDADE[formato] in montar_sistema_critico(OBJ, params(), formato)
    assert MARCAS_QUALIDADE[formato] in montar_sistema_auditor(params(), formato)


def test_sem_formato_monta_proposicao():
    """A e1a4c8f02b77 chama registrar_versao com o código atual, sem formato."""
    assert montar_sistema(OBJ, params()) == montar_sistema(
        OBJ, params(), FormatoItem.PROPOSICAO
    )


def test_exemplos_do_formato_vao_so_para_o_gerador():
    assert "<exemplo_afirmativas>" in montar_sistema(OBJ, params(), FormatoItem.AFIRMATIVAS)
    assert "<exemplo_afirmativas>" not in montar_sistema_critico(
        OBJ, params(), FormatoItem.AFIRMATIVAS
    )


@pytest.mark.parametrize("tipo", [OBJ, DISC])
def test_contextualizacao_e_bloom_no_gerador_e_no_critico(tipo):
    for texto in (montar_sistema(tipo, params()), montar_sistema_critico(tipo, params())):
        assert "<contextualizacao>" in texto
        assert "<nivel_bloom>" in texto


def test_discursiva_nao_lista_discuta_como_verbo_de_comando():
    texto = montar_sistema(DISC, params())
    assert "<itens>" in texto
    assert "discuta, relacione" not in texto


def test_modulos_de_formato_entram_no_hash_de_versao():
    """`carregar_modulos_versionados` usa rglob: editar um módulo de formato
    muda o hash, e a geração para até haver versão nova."""
    nomes = [n for n, _ in carregar_modulos_versionados()]
    assert "objetiva/formatos/afirmativas/01_formato.md" in nomes
    assert "objetiva/formatos/assercao_razao/01_formato.md" in nomes
