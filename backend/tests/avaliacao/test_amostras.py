"""Amostras do RAGAS a partir de questões — função pura, sem banco nem rede.

As questões aqui são `SimpleNamespace`: `amostras.py` só lê atributos, então não
precisa do ORM (e o teste não precisa do Postgres).
"""

from types import SimpleNamespace as NS

from avaliacao.amostras import (
    contextos_das_fontes,
    montar_amostra,
    montar_amostras,
)
from backend.app.domain import FormatoItem, TipoQuestao


def _fonte(trecho: str, localizacao: str = "página 3") -> NS:
    return NS(trecho_base=trecho, localizacao=localizacao)


def _objetiva(**campos) -> NS:
    base = dict(
        id=1,
        numero=1,
        tipo=TipoQuestao.OBJETIVA,
        formato=FormatoItem.PROPOSICAO,
        enunciado="Qual a capital do Maranhão?",
        tema="Geografia",
        alternativas=[
            NS(letra="A", texto="Teresina", correta=False),
            NS(letra="B", texto="São Luís", correta=True),
        ],
        justificativa=NS(
            justificativa_correta="São Luís é a capital, conforme o material.",
            estrutura_formato={"contexto": "x"},
        ),
        aspectos=[],
        fontes_internas=[_fonte("São Luís é a capital do estado.")],
    )
    base.update(campos)
    return NS(**base)


def test_objetiva_junta_enunciado_gabarito_e_justificativa():
    questao = _objetiva()

    amostra = montar_amostra(questao, ["São Luís é a capital do estado."])

    assert amostra["user_input"] == "Geografia"
    assert amostra["retrieved_contexts"] == ["São Luís é a capital do estado."]
    resposta = amostra["response"]
    assert "Qual a capital do Maranhão?" in resposta
    assert "Gabarito: B) São Luís" in resposta
    assert "São Luís é a capital, conforme o material." in resposta
    assert "Teresina" not in resposta


def test_sem_tema_a_pergunta_vira_o_enunciado():
    amostra = montar_amostra(_objetiva(tema=None), ["trecho"])

    assert amostra["user_input"] == "Qual a capital do Maranhão?"


def test_objetiva_sem_justificativa_nao_escreve_none():
    amostra = montar_amostra(_objetiva(justificativa=None), ["trecho"])

    assert "None" not in amostra["response"]
    assert "Gabarito: B) São Luís" in amostra["response"]


def test_discursiva_usa_aspectos_esperados_na_ordem_no_lugar_de_alternativas():
    questao = _objetiva(
        tipo=TipoQuestao.DISCURSIVA,
        alternativas=[],
        aspectos=[
            NS(ordem=2, texto="Cita a Lei Y."),
            NS(ordem=1, texto="Define o conceito X."),
        ],
    )

    resposta = montar_amostra(questao, ["trecho"])["response"]

    assert "Gabarito" not in resposta
    assert resposta.index("Define o conceito X.") < resposta.index("Cita a Lei Y.")


def test_calculo_leva_a_formula_citada_e_nao_o_resultado_numerico():
    questao = _objetiva(
        formato=FormatoItem.CALCULO,
        enunciado="Um corpo tem massa de 2 kg e aceleração de 3 m/s². Calcule a força.",
        alternativas=[
            NS(letra="A", texto="6 N", correta=True),
            NS(letra="B", texto="5 N", correta=False),
        ],
        justificativa=NS(
            justificativa_correta=r"\(F = 2 \cdot 3 = 6\ \text{N}\)",
            estrutura_formato={"formula_citada": "F = m · a"},
        ),
    )

    resposta = montar_amostra(questao, ["Segunda lei: F = m · a."])["response"]

    assert "F = m · a" in resposta
    assert "Calcule a força" in resposta
    # O número é calculado pelo Núcleo Determinístico, não vem do material:
    # entrar como "afirmação" faria o juiz reprovar o que o sistema garante.
    assert "6 N" not in resposta
    assert "cdot" not in resposta


def test_contextos_das_fontes_tira_vazios_e_repetidos_mantendo_a_ordem():
    questao = _objetiva(
        fontes_internas=[
            _fonte("primeiro"),
            _fonte("   "),
            _fonte("segundo"),
            _fonte("primeiro"),
        ]
    )

    assert contextos_das_fontes(questao) == ["primeiro", "segundo"]


def test_montar_amostras_pula_e_conta_item_sem_fonte():
    com_fonte = _objetiva(id=10)
    sem_fonte = _objetiva(id=11, fontes_internas=[])

    montagem = montar_amostras([com_fonte, sem_fonte])

    assert [a["user_input"] for a in montagem.amostras] == ["Geografia"]
    assert montagem.ids == [10]
    assert montagem.puladas == [(11, "sem contexto")]


def test_montar_amostras_prefere_os_contextos_recuperados_quando_dados():
    questao = _objetiva(id=7)

    montagem = montar_amostras([questao], {7: ["top-1", "top-2"]})

    assert montagem.amostras[0]["retrieved_contexts"] == ["top-1", "top-2"]


def test_contexto_recuperado_vazio_pula_mesmo_havendo_fonte_citada():
    questao = _objetiva(id=7)

    montagem = montar_amostras([questao], {7: []})

    assert montagem.amostras == []
    assert montagem.puladas == [(7, "sem contexto")]


def test_aceita_os_nomes_em_maiuscula_que_o_postgres_grava():
    questao = _objetiva(
        tipo="DISCURSIVA",
        formato="PROPOSICAO",
        alternativas=[],
        aspectos=[NS(ordem=1, texto="Define X.")],
    )

    assert "Aspectos esperados" in montar_amostra(questao, ["t"])["response"]
