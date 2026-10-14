import pytest

from backend.app.domain import EstadoQuestao, EventoBanco, FormatoItem
from backend.app.exceptions import InconsistenciaDeEstadoException
from backend.app.services.controle_banco.estado import registrar_relatorio
from backend.app.services.controle_banco.leitura import (
    ler_banco,
    listar_relatorios,
    questao_lida,
)
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)


def banco_misto(db, sessao):
    banco = criar_banco(db, sessao, n_objetivas=3, n_discursivas=2)
    for numero in (1, 2, 3):
        criar_questao_objetiva(db, banco, numero=numero)
    for numero in (4, 5):
        criar_questao_discursiva(db, banco, numero=numero)
    db.commit()
    return banco


def test_le_o_bloco_pedido_em_ordem_de_numero(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    lido = ler_banco(db_session, docente, banco.id, 2, 4, False, False)
    assert [q.numero for q in lido.questoes] == [2, 3, 4]


def test_cabecalho_traz_rotulo_e_alvos_por_tipo(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    lido = ler_banco(db_session, docente, banco.id, 1, 20, False, False)
    assert lido.rotulo == "v1.r0"
    assert (lido.n_alvo, lido.n_alvo_objetivas, lido.n_alvo_discursivas) == (5, 3, 2)
    assert lido.n_atual == 5
    assert lido.ultimo_relatorio is None


def test_cabecalho_traz_o_ultimo_relatorio(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    registrar_relatorio(db_session, banco, EventoBanco.EXCLUSAO)
    registrar_relatorio(db_session, banco, EventoBanco.EXCLUSAO)
    db_session.commit()
    lido = ler_banco(db_session, docente, banco.id, 1, 20, False, False)
    assert lido.revisao == 2
    assert lido.rotulo == "v1.r2"
    assert lido.ultimo_relatorio.revisao == 2


def test_gabarito_escondido_por_padrao(db_session, docente, sessao_rascunho):
    """nada de gabarito salvo pedido explícito."""
    banco = banco_misto(db_session, sessao_rascunho)
    lido = ler_banco(db_session, docente, banco.id, 1, 20, False, False)
    objetiva = next(q for q in lido.questoes if q.alternativas)
    discursiva = next(q for q in lido.questoes if not q.alternativas)
    assert objetiva.letra_correta is None
    assert [a.letra for a in objetiva.alternativas] == ["A", "B", "C", "D", "E"]
    assert discursiva.aspectos_esperados == []


def test_com_gabarito_traz_correta_e_aspectos(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    lido = ler_banco(db_session, docente, banco.id, 1, 20, True, False)
    objetiva = next(q for q in lido.questoes if q.alternativas)
    discursiva = next(q for q in lido.questoes if not q.alternativas)
    assert objetiva.letra_correta == "A"
    assert [a.ordem for a in discursiva.aspectos_esperados] == [1, 2]
    assert discursiva.aspectos_esperados[0].fonte.identificador_material == "P1"


def test_historico_so_aparece_com_o_parametro(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    criar_questao_objetiva(
        db_session, banco, numero=1, estado=EstadoQuestao.SUBSTITUIDA
    )
    criar_questao_objetiva(db_session, banco, numero=1, estado=EstadoQuestao.CANDIDATA)
    db_session.commit()

    sem = ler_banco(db_session, docente, banco.id, 1, 1, False, False)
    assert [q.estado for q in sem.questoes] == [EstadoQuestao.ATIVA]

    com = ler_banco(db_session, docente, banco.id, 1, 1, False, True)
    assert sorted(q.estado.value for q in com.questoes) == [
        "ativa",
        "candidata",
        "substituida",
    ]


def test_leitura_traz_fonte_e_violacoes_e_nunca_o_rascunho(
    db_session, docente, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    criar_questao_objetiva(
        db_session,
        banco,
        numero=1,
        violacoes_final=[
            {"regra": "correta_longa", "alvo": "A", "detalhe": "a correta é longa"}
        ],
    )
    db_session.commit()
    lido = ler_banco(db_session, docente, banco.id, 1, 20, True, False)
    questao = lido.questoes[0]
    assert questao.fontes[0].identificador_material == "P1"
    assert questao.fontes[0].trecho_base.startswith("trecho que sustenta")
    assert questao.violacoes[0]["regra"] == "correta_longa"
    # O dataclass não tem onde guardar justificativa nem rascunho: é estrutural.
    assert not hasattr(questao, "justificativa")
    assert not hasattr(questao, "rascunho")


def test_leitura_de_banco_incoerente_levanta(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    banco.n_atual = 99
    db_session.commit()
    with pytest.raises(InconsistenciaDeEstadoException):
        ler_banco(db_session, docente, banco.id, 1, 20, False, False)


def test_listar_relatorios_em_ordem_de_revisao(db_session, docente, sessao_rascunho):
    banco = banco_misto(db_session, sessao_rascunho)
    registrar_relatorio(db_session, banco, EventoBanco.EXCLUSAO)
    registrar_relatorio(db_session, banco, EventoBanco.CONGELAMENTO)
    db_session.commit()
    relatorios = listar_relatorios(db_session, docente, banco.id)
    assert [r.revisao for r in relatorios] == [1, 2]


def test_leitura_nao_faz_uma_consulta_por_questao(db_session, docente, sessao_rascunho):
    """N+1: o número de SELECTs não pode crescer com o número de questões."""
    from backend.tests.contagem_queries import contar_queries

    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=12, n_discursivas=8)
    for numero in range(1, 13):
        criar_questao_objetiva(db_session, banco, numero=numero)
    for numero in range(13, 21):
        criar_questao_discursiva(db_session, banco, numero=numero)
    db_session.commit()

    with contar_queries(db_session) as consultas:
        lido = ler_banco(db_session, docente, banco.id, 1, 20, True, False)

    assert len(lido.questoes) == 20
    assert len(consultas) <= 20, f"{len(consultas)} SELECTs para 20 questões"


def test_leitura_traz_formato_e_item_do_aspecto(db_session, docente, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_discursivas=1)
    questao = criar_questao_discursiva(db_session, banco, numero=1, aspectos=2)
    for aspecto, item in zip(questao.aspectos, (1, 2), strict=True):
        aspecto.item = item
    db_session.commit()
    lida = questao_lida(questao, com_gabarito=True)
    assert lida.formato is FormatoItem.PROPOSICAO
    assert [a.item for a in lida.aspectos_esperados] == [1, 2]
