import pytest

from backend.app.exceptions import PlaceholderNaoResolvidoException
from backend.app.prompt.montagem import (
    calcular_hash,
    carregar_modulos,
    carregar_modulos_critico,
    carregar_modulos_versionados,
    montar_sistema,
    montar_sistema_critico,
)
from backend.app.prompt.parametros import ParametrosGeracao


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


def test_carrega_os_quatro_modulos_em_ordem():
    nomes = [nome for nome, _ in carregar_modulos()]
    assert nomes == [
        "01_identidade.md",
        "02_qualidade_alternativas.md",
        "03_politica_fontes.md",
        "04_exemplos.md",
    ]


def test_montagem_injeta_todos_os_placeholders():
    texto = montar_sistema(params())
    assert "Algoritmos" in texto
    assert "2026.2" in texto
    assert "Computação" in texto
    assert "Grafos" in texto
    assert "exatamente 5 alternativas" in texto
    assert "30 médias" in texto


def test_montagem_nao_deixa_placeholder_literal():
    assert "{{" not in montar_sistema(params())


def test_placeholder_faltando_levanta_excecao(tmp_path, monkeypatch):
    from backend.app.prompt import montagem

    (tmp_path / "01_teste.md").write_text("Disciplina: {{disciplina}} e {{inexistente}}")
    monkeypatch.setattr(montagem, "DIRETORIO_MODULOS", tmp_path)
    with pytest.raises(PlaceholderNaoResolvidoException, match="inexistente"):
        montar_sistema(params())


def test_campos_opcionais_nulos_viram_texto_legivel():
    texto = montar_sistema(params(area_do_conhecimento=None, tema_escopo=None))
    assert "{{" not in texto
    assert "não informada" in texto or "não informado" in texto


def test_prompt_montado_nao_tem_vocabulario_medico():
    texto = montar_sistema(params()).lower()
    for proibido in ("medicina", "fisiopatológico", "clínico", "livro oficial"):
        assert proibido not in texto


def test_hash_e_deterministico_e_sensivel_ao_conteudo():
    modulos = carregar_modulos()
    assert calcular_hash(modulos) == calcular_hash(modulos)
    alterado = [(modulos[0][0], modulos[0][1] + "x"), *modulos[1:]]
    assert calcular_hash(alterado) != calcular_hash(modulos)


@pytest.mark.parametrize("k", [2, 5, 11])
def test_k_nas_pontas_da_faixa_permitida(k):
    texto = montar_sistema(params(k_alternativas=k))
    assert f"exatamente {k} alternativas" in texto


def test_modulos_do_critico_ficam_fora_do_gerador():
    """carregar_modulos() junta a raiz. Um .md do crítico ali seria colado no
    prompt do Gerador."""
    assert "<revisor>" not in montar_sistema(params())


def test_sistema_do_critico_reusa_qualidade_e_fontes():
    texto = montar_sistema_critico(params())
    assert texto.index("<revisor>") < texto.index("<qualidade_alternativas>")
    assert texto.index("<qualidade_alternativas>") < texto.index("<politica_fontes>")
    # Persona do gerador e few-shot ficam de fora: orçamento de contexto.
    assert "<identidade>" not in texto
    assert "<exemplos>" not in texto
    assert "{{" not in texto
    assert "exatamente 5 alternativas" in texto


def test_modulos_do_critico_levam_o_caminho_relativo_no_nome():
    assert [nome for nome, _ in carregar_modulos_critico()] == ["critico/01_revisor.md"]


def test_hash_versionado_cobre_o_critico():
    assert calcular_hash(carregar_modulos_versionados()) != calcular_hash(
        carregar_modulos()
    )


def test_mover_modulo_entre_pastas_muda_o_hash():
    assert calcular_hash([("critico/x.md", "a")]) != calcular_hash([("x.md", "a")])


def test_regra_1_usa_media_das_demais():
    """ diz "das demais"; "do conjunto" dá outro número."""
    texto = montar_sistema(params())
    assert "média de palavras das demais alternativas" in texto
    assert "média de palavras do conjunto" not in texto
