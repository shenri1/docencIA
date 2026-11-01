import json

import pytest
from pydantic import ValidationError

from backend.app.domain import NivelBloom, TipoQuestao
from backend.app.schemas.geracao import (
    LETRAS,
    MAX_FONTES,
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
            "contexto": "",
            "comando": "Qual estrutura a busca em largura utiliza?",
            "nivel_bloom": "aplicar",
            "tema": "Grafos",
            "subtema": "Busca em largura",
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
                    {"letra": "ABCDEFGHIJK"[i % k], "motivo": f"distrator {i}"}
                    for i in range(
                        1, (invalidacoes if invalidacoes is not None else k - 1) + 1
                    )
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
    """\"Criar\" fica fora da múltipla escolha: síntese original não é
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
            "contexto": "",
            "comando": "Proponha uma variação da busca em largura para grafos ponderados.",
            "nivel_bloom": nivel_bloom,
            "tema": "Grafos",
            "subtema": "Busca em largura",
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
    resultado = (
        montar_schema_discursiva()
        .model_validate(
            {
                "resultado": {
                    "tipo": "insuficiencia_de_fonte",
                    "informacao_faltante": "x",
                }
            }
        )
        .resultado
    )
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


def test_schema_objetiva_exige_subtema():
    corpo = corpo_questao(5)["resultado"]
    del corpo["subtema"]
    with pytest.raises(ValidationError):
        montar_schema_objetiva(5).model_validate({"resultado": corpo})


def test_schema_discursiva_exige_subtema():
    corpo = corpo_discursiva()["resultado"]
    del corpo["subtema"]
    with pytest.raises(ValidationError):
        montar_schema_discursiva().model_validate({"resultado": corpo})


def test_invalidacao_exige_letra():
    corpo = corpo_questao(5)
    corpo["resultado"]["justificativa"]["invalidacao_distratores"] = ["sem letra"] * 4
    with pytest.raises(ValidationError):
        montar_schema_objetiva(5).model_validate(corpo)


def test_letra_da_invalidacao_e_fechada_em_k():
    corpo = corpo_questao(3)
    corpo["resultado"]["justificativa"]["invalidacao_distratores"] = [
        {"letra": "B", "motivo": "x"},
        {"letra": "E", "motivo": "y"},  # K=3: só A, B, C existem
    ]
    with pytest.raises(ValidationError):
        montar_schema_objetiva(3).model_validate(corpo)


def test_json_schema_fecha_a_letra_da_invalidacao_por_enum():
    gerado = montar_schema_objetiva(4).model_json_schema()
    invalidacao = gerado["$defs"]["InvalidacaoGerada4"]
    assert invalidacao["properties"]["letra"]["enum"] == ["A", "B", "C", "D"]


def test_objetiva_tem_contexto_antes_do_comando_e_nao_tem_enunciado():
    questao = _questao_objetiva(montar_schema_objetiva(5).model_json_schema())
    campos = list(questao["properties"])
    assert "enunciado" not in campos
    assert (
        campos.index("contexto")
        < campos.index("comando")
        < campos.index("alternativas")
    )


def test_discursiva_tem_contexto_antes_do_comando():
    questao = _questao_discursiva(montar_schema_discursiva().model_json_schema())
    campos = list(questao["properties"])
    assert "enunciado" not in campos
    assert campos.index("contexto") < campos.index("comando")


from backend.app.domain import FormatoItem
from backend.tests.services.geracao.duplos import (
    corpo_afirmativas,
    corpo_assercao,
    corpo_discursiva_itens,
)


def _questao_de(esquema):
    return next(d for nome, d in esquema["$defs"].items() if nome.startswith("Questao"))


def test_afirmativas_fixam_o_valor_por_posicao():
    cfg = (True, False, True)
    esquema = montar_schema(TipoQuestao.OBJETIVA, 5, FormatoItem.AFIRMATIVAS, cfg)
    js = esquema.model_json_schema()
    campos = list(_questao_de(js)["properties"])
    assert campos[:5] == [
        "tipo",
        "contexto",
        "comando",
        "afirmativa_i",
        "afirmativa_ii",
    ]
    assert "afirmativa_iv" not in campos
    assert "alternativas" not in campos and "letra_correta" not in campos
    esquema.model_validate(corpo_afirmativas(cfg))
    with pytest.raises(ValidationError):
        esquema.model_validate(corpo_afirmativas((True, True, True)))


def test_afirmativas_com_k_grande_tem_quatro():
    cfg = (True, False, True, False)
    esquema = montar_schema(TipoQuestao.OBJETIVA, 9, FormatoItem.AFIRMATIVAS, cfg)
    assert "afirmativa_iv" in _questao_de(esquema.model_json_schema())["properties"]


def test_afirmativas_recusa_configuracao_do_tamanho_errado():
    with pytest.raises(ValueError):
        montar_schema(
            TipoQuestao.OBJETIVA, 9, FormatoItem.AFIRMATIVAS, (True, False, True)
        )


def test_assercao_nao_tem_comando_nem_alternativas():
    esquema = montar_schema(TipoQuestao.OBJETIVA, 5, FormatoItem.ASSERCAO_RAZAO, "vf")
    campos = list(_questao_de(esquema.model_json_schema())["properties"])
    assert campos[:3] == ["tipo", "contexto", "assercao"]
    assert "comando" not in campos and "alternativas" not in campos
    esquema.model_validate(corpo_assercao())


def test_discursiva_com_itens_fixa_o_numero_de_itens():
    esquema = montar_schema(TipoQuestao.DISCURSIVA, 5, n_itens=3)
    campos = list(_questao_de(esquema.model_json_schema())["properties"])
    assert campos.index("contexto") < campos.index("itens")
    esquema.model_validate(corpo_discursiva_itens(3))
    with pytest.raises(ValidationError):
        esquema.model_validate(corpo_discursiva_itens(2))


# --- Fonte restrita aos trechos enviados ---



def _restringe_a(esquema, *identificadores: str) -> bool:
    """Um valor só sai como `const`, mais de um como `enum`."""
    texto = json.dumps(esquema.model_json_schema())
    if len(identificadores) == 1:
        return f'"const": "{identificadores[0]}"' in texto
    return f'"enum": {json.dumps(list(identificadores))}' in texto


def _com_fonte(corpo: dict, identificador: str) -> dict:
    corpo["resultado"]["fontes"][0]["identificador_material"] = identificador
    return corpo


@pytest.mark.parametrize("identificador", ["P1, página 10", "S1", "P3"])
def test_identificador_fora_dos_trechos_e_recusado_pelo_schema(identificador):
    """qwen2.5:3b escrevia o rótulo inteiro ("P1, página 10") ou um material que
    não veio; com o enum, a decodificação restrita não deixa."""
    esquema = montar_schema(TipoQuestao.OBJETIVA, 5, identificadores=["P1", "P2"])
    with pytest.raises(ValidationError):
        esquema.model_validate(_com_fonte(corpo_questao(5), identificador))
    esquema.model_validate(_com_fonte(corpo_questao(5), "P2"))


def test_identificador_vira_enum_no_json_schema():
    esquema = montar_schema(
        TipoQuestao.OBJETIVA, 5, identificadores=["P2", "P1", "P2"]
    )
    assert _restringe_a(esquema, "P1", "P2")


@pytest.mark.parametrize(
    ("formato", "configuracao"),
    [
        (FormatoItem.AFIRMATIVAS, (True, False, True)),
        (FormatoItem.ASSERCAO_RAZAO, "vf"),
        (FormatoItem.CALCULO, None),
    ],
)
def test_todo_formato_objetivo_restringe_a_fonte(formato, configuracao):
    esquema = montar_schema(
        TipoQuestao.OBJETIVA, 5, formato, configuracao, identificadores=["P1"]
    )
    assert _restringe_a(esquema, "P1")


@pytest.mark.parametrize("n_itens", [None, 2])
def test_discursiva_restringe_a_fonte_do_aspecto(n_itens):
    esquema = montar_schema(
        TipoQuestao.DISCURSIVA, 5, n_itens=n_itens, identificadores=["P1"]
    )
    assert _restringe_a(esquema, "P1")
    if n_itens is None:
        corpo = corpo_discursiva()
        corpo["resultado"]["aspectos_esperados"][0]["fonte"][
            "identificador_material"
        ] = "S1"
        with pytest.raises(ValidationError):
            esquema.model_validate(corpo)
        esquema.model_validate(corpo_discursiva())


def test_fontes_tem_teto():
    """Lista sem teto deixa modelo pequeno repetir o item até cortar a resposta."""
    corpo = corpo_questao(5)
    corpo["resultado"]["fontes"] *= MAX_FONTES + 1
    with pytest.raises(ValidationError):
        montar_schema_objetiva(5).model_validate(corpo)
