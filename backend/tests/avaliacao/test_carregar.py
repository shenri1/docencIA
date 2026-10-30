"""Linhas de SQL → objetos que `amostras.py` lê. A consulta em si não é testada
aqui (exige Postgres); a montagem, que é onde as regras estão, é."""

from avaliacao.carregar import montar_questoes


def _q(id_, **extra):
    return {
        "id": id_,
        "numero": id_,
        "tipo": "OBJETIVA",
        "formato": "PROPOSICAO",
        "enunciado": f"enunciado {id_}",
        "tema": "t",
        **extra,
    }


def test_agrupa_filhos_pela_questao_e_mantem_a_ordem_das_questoes():
    questoes = montar_questoes(
        questoes=[_q(2), _q(1)],
        alternativas=[
            {"questao_id": 1, "letra": "A", "texto": "a", "correta": True},
            {"questao_id": 2, "letra": "A", "texto": "b", "correta": False},
        ],
        fontes=[{"questao_id": 1, "localizacao": "página 1", "trecho_base": "x"}],
        justificativas=[
            {
                "questao_id": 1,
                "justificativa_correta": "porque",
                "estrutura_formato": {"contexto": "c"},
            }
        ],
        aspectos=[{"questao_id": 2, "ordem": 1, "texto": "asp"}],
    )

    assert [q.id for q in questoes] == [2, 1]
    q2, q1 = questoes
    assert [a.letra for a in q1.alternativas] == ["A"]
    assert q1.fontes_internas[0].trecho_base == "x"
    assert q1.justificativa.justificativa_correta == "porque"
    assert q2.justificativa is None
    assert q2.fontes_internas == []
    assert q2.aspectos[0].texto == "asp"
