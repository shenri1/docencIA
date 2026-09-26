import json

import pytest

from backend.app.domain import NivelBloom, TipoQuestao
from backend.app.schemas.geracao import (
    LETRAS,
    AlternativaGerada,
    InsuficienciaFonte,
    montar_schema,
    montar_schema_discursiva,
    montar_schema_objetiva,
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
    esquema = montar_schema_objetiva(k).model_json_schema()
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
    bruto = json.dumps(montar_schema_objetiva(5).model_json_schema())
    assert "oneOf" in bruto
    assert "discriminator" in bruto


def _questao_objetiva(esquema: dict) -> dict:
    return next(
        v for nome, v in esquema["$defs"].items() if nome.startswith("QuestaoGerada")
    )


def test_bloom_da_objetiva_e_vocabulario_fechado_sem_criar():
    """O remove "Criar" da múltipla escolha: síntese original não é
    operacionalizável numa alternativa. A decodificação restrita o impede."""
    campo = _questao_objetiva(montar_schema_objetiva(5).model_json_schema())[
        "properties"
    ]["nivel_bloom"]
    assert campo["enum"] == ["lembrar", "entender", "aplicar", "analisar", "avaliar"]


def test_faixa_dificuldade_nao_esta_no_schema_de_saida():
    """O código já sabe a faixa pela distribuição; pedir ao modelo que a repita
    só cria divergência possível."""
    assert "faixa_dificuldade" not in json.dumps(
        montar_schema_objetiva(5).model_json_schema()
    )


def test_ramo_questao_valida():
    resultado = montar_schema_objetiva(5).model_validate(corpo_questao(5)).resultado
    assert resultado.tipo == "questao"
    assert len(resultado.alternativas) == 5
    assert resultado.nivel_bloom == "aplicar"


def test_objetiva_rejeita_criar():
    corpo = corpo_questao(5)
    corpo["resultado"]["nivel_bloom"] = "criar"
    with pytest.raises(ValueError):
        montar_schema_objetiva(5).model_validate(corpo)


def test_ramo_insuficiencia_valida():
    modelo = montar_schema_objetiva(5)
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
    modelo = montar_schema_objetiva(5)
    with pytest.raises(ValueError):
        modelo.model_validate(corpo_questao(5, invalidacoes=2))


def test_k_fora_da_faixa_permitida_e_erro_de_programacao():
    for k in (1, 12):
        with pytest.raises(ValueError):
            montar_schema_objetiva(k)


def _questao(esquema: dict) -> dict:
    return next(
        v for nome, v in esquema["$defs"].items() if nome.startswith("QuestaoGerada")
    )


@pytest.mark.parametrize("k", [2, 4, 11])
def test_letra_correta_e_enum_das_k_primeiras_letras(k):
    """Um único campo enum torna zero ou duas corretas irrepresentáveis: a
    decodificação restrita não consegue emitir outra coisa."""
    esquema = montar_schema_objetiva(k).model_json_schema()
    campo = _questao(esquema)["properties"]["letra_correta"]
    assert campo["enum"] == list(LETRAS[:k])


def test_letra_correta_fora_das_k_letras_e_rejeitada():
    with pytest.raises(ValueError):
        montar_schema_objetiva(4).model_validate(corpo_questao(4, letra_correta="E"))


def test_alternativa_nao_carrega_letra_nem_correta():
    """Letra é posição, atribuída pelo código; correta é o campo da questão.
    Deixá-las com o modelo permitia letra duplicada e 0 ou 2 corretas."""
    propriedades = AlternativaGerada.model_json_schema()["properties"]
    assert set(propriedades) == {"texto", "e_gemeo_malvado"}


def corpo_discursiva(aspectos: int = 2, nivel_bloom: str = "criar") -> dict:
    return {
        "resultado": {
            "tipo": "questao_discursiva",
            "enunciado": "Proponha uma variação da busca em largura para grafos ponderados.",
            "nivel_bloom": nivel_bloom,
            "tema": "Grafos",
            "objetivo_cognitivo": "propor adaptação de algoritmo",
            "aspectos_esperados": [
                {
                    "texto": f"aspecto {i}",
                    "fonte": {
                        "identificador_material": "P1",
                        "localizacao": "página 12",
                        "trecho_base": "A busca em largura usa uma fila.",
                    },
                }
                for i in range(aspectos)
            ],
        }
    }


def _questao_discursiva(esquema: dict) -> dict:
    return next(
        v
        for nome, v in esquema["$defs"].items()
        if nome.startswith("QuestaoDiscursivaGerada")
    )


def test_discursiva_limita_aspectos_entre_2_e_5():
    campo = _questao_discursiva(montar_schema_discursiva().model_json_schema())[
        "properties"
    ]["aspectos_esperados"]
    assert campo["minItems"] == 2
    assert campo["maxItems"] == 5


@pytest.mark.parametrize("aspectos", [1, 6])
def test_discursiva_rejeita_aspectos_fora_da_faixa(aspectos):
    with pytest.raises(ValueError):
        montar_schema_discursiva().model_validate(corpo_discursiva(aspectos))


def test_aspecto_sem_fonte_e_irrepresentavel():
    corpo = corpo_discursiva()
    del corpo["resultado"]["aspectos_esperados"][0]["fonte"]
    with pytest.raises(ValueError):
        montar_schema_discursiva().model_validate(corpo)


def test_discursiva_aceita_criar():
    resultado = montar_schema_discursiva().model_validate(corpo_discursiva()).resultado
    assert resultado.nivel_bloom is NivelBloom.CRIAR
    assert resultado.aspectos_esperados[0].fonte.identificador_material == "P1"


def test_discursiva_tem_uniao_com_insuficiencia():
    resultado = montar_schema_discursiva().model_validate(
        {"resultado": {"tipo": "insuficiencia_de_fonte", "informacao_faltante": "x"}}
    ).resultado
    assert isinstance(resultado, InsuficienciaFonte)


def test_discursiva_nao_tem_alternativas_nem_letra():
    bruto = json.dumps(montar_schema_discursiva().model_json_schema())
    assert "alternativas" not in bruto
    assert "letra_correta" not in bruto


def test_montar_schema_escolhe_pelo_tipo():
    esquema_obj = montar_schema(TipoQuestao.OBJETIVA, 4).model_json_schema()
    assert "alternativas" in json.dumps(esquema_obj)
    assert "letra_correta" in json.dumps(esquema_obj)
    esquema = montar_schema(TipoQuestao.DISCURSIVA, 4).model_json_schema()
    assert "aspectos_esperados" in json.dumps(esquema)
