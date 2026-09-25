import json

import pytest

from backend.app.domain import NivelBloom
from backend.app.schemas.geracao import (
    LETRAS,
    AlternativaGerada,
    InsuficienciaFonte,
    montar_schema_questao,
)


def corpo_questao(
    k: int, invalidacoes: int | None = None, letra_correta: str = "A"
) -> dict:
    return {
        "resultado": {
            "tipo": "questao",
            "enunciado": "Qual estrutura a busca em largura utiliza?",
            "nivel_bloom": "aplicar",
            "tema": "Grafos",
            "alternativas": [
                {"texto": f"opção {i}", "e_gemeo_malvado": i == 1} for i in range(k)
            ],
            "letra_correta": letra_correta,
            "fontes": [
                {
                    "identificador_material": "P1",
                    "localizacao": "página 12",
                    "trecho_base": "A busca em largura usa uma fila.",
                }
            ],
            "justificativa": {
                "objetivo_cognitivo": "identificar a estrutura correta",
                "justificativa_correta": "o trecho afirma o uso de fila",
                "invalidacao_distratores": [
                    f"distrator {i}"
                    for i in range(invalidacoes if invalidacoes is not None else k - 1)
                ],
                "verificacao_unicidade": True,
                "texto_verificacao_unicidade": "nenhuma errada é defensável",
            },
        }
    }


@pytest.mark.parametrize("k", [2, 5, 11])
def test_schema_fixa_a_contagem_de_alternativas_e_invalidacoes(k):
    """Medido contra o Ollama: minItems/maxItems são honrados pela
    decodificação restrita. É isto que impõe em vez de esperá-la."""
    esquema = montar_schema_questao(k).model_json_schema()
    definicoes = esquema["$defs"]
    questao = next(
        v for nome, v in definicoes.items() if nome.startswith("QuestaoGerada")
    )
    justificativa = next(
        v for nome, v in definicoes.items() if nome.startswith("JustificativaGerada")
    )
    assert questao["properties"]["alternativas"]["minItems"] == k
    assert questao["properties"]["alternativas"]["maxItems"] == k
    assert justificativa["properties"]["invalidacao_distratores"]["minItems"] == k - 1
    assert justificativa["properties"]["invalidacao_distratores"]["maxItems"] == k - 1


def test_schema_tem_uniao_discriminada():
    bruto = json.dumps(montar_schema_questao(5).model_json_schema())
    assert "oneOf" in bruto
    assert "discriminator" in bruto


def test_nivel_bloom_entra_como_enum_e_nao_string_livre():
    """Com `str`, o modelo devolveu "media" — faixa de dificuldade no campo de
    Bloom. O enum torna esse valor inalcançável."""
    definicoes = montar_schema_questao(5).model_json_schema()["$defs"]
    assert set(definicoes["NivelBloom"]["enum"]) == {n.value for n in NivelBloom}


def test_faixa_dificuldade_nao_esta_no_schema_de_saida():
    """O código já sabe a faixa pela distribuição; pedir ao modelo que a repita
    só cria divergência possível."""
    assert "faixa_dificuldade" not in json.dumps(
        montar_schema_questao(5).model_json_schema()
    )


def test_ramo_questao_valida():
    modelo = montar_schema_questao(5)
    resultado = modelo.model_validate(corpo_questao(5)).resultado
    assert resultado.tipo == "questao"
    assert len(resultado.alternativas) == 5
    assert resultado.nivel_bloom is NivelBloom.APLICAR


def test_ramo_insuficiencia_valida():
    modelo = montar_schema_questao(5)
    resultado = modelo.model_validate(
        {
            "resultado": {
                "tipo": "insuficiencia_de_fonte",
                "informacao_faltante": "não há trecho definindo o critério de parada",
            }
        }
    ).resultado
    assert isinstance(resultado, InsuficienciaFonte)
    assert "critério de parada" in resultado.informacao_faltante


def test_contagem_errada_de_invalidacoes_e_rejeitada():
    modelo = montar_schema_questao(5)
    with pytest.raises(ValueError):
        modelo.model_validate(corpo_questao(5, invalidacoes=2))


def test_k_fora_da_faixa_permitida_e_erro_de_programacao():
    for k in (1, 12):
        with pytest.raises(ValueError):
            montar_schema_questao(k)


def _questao(esquema: dict) -> dict:
    return next(
        v for nome, v in esquema["$defs"].items() if nome.startswith("QuestaoGerada")
    )


@pytest.mark.parametrize("k", [2, 4, 11])
def test_letra_correta_e_enum_das_k_primeiras_letras(k):
    """Um único campo enum torna zero ou duas corretas irrepresentáveis: a
    decodificação restrita não consegue emitir outra coisa."""
    esquema = montar_schema_questao(k).model_json_schema()
    campo = _questao(esquema)["properties"]["letra_correta"]
    assert campo["enum"] == list(LETRAS[:k])


def test_letra_correta_fora_das_k_letras_e_rejeitada():
    with pytest.raises(ValueError):
        montar_schema_questao(4).model_validate(corpo_questao(4, letra_correta="E"))


def test_alternativa_nao_carrega_letra_nem_correta():
    """Letra é posição, atribuída pelo código; correta é o campo da questão.
    Deixá-las com o modelo permitia letra duplicada e 0 ou 2 corretas."""
    propriedades = AlternativaGerada.model_json_schema()["properties"]
    assert set(propriedades) == {"texto", "e_gemeo_malvado"}
