import pytest

from backend.app.domain import (
    EstadoBanco,
    EstadoProva,
    EstadoSessao,
    FaixaDificuldade,
)
from backend.app.exceptions import (
    BancoNaoCongeladoException,
    InconsistenciaDeEstadoException,
    MontagemInconsistenteException,
    ProvasJaMontadasException,
    QuestoesIndisponiveisException,
    RevisaoDesatualizadaException,
    SobreposicaoInevitavelException,
)
from backend.app.models.provas import ItemProva, Prova
from backend.app.services.controle_banco.exclusao_service import congelar_banco
from backend.app.services.provas import montagem_service
from backend.app.services.provas.montagem_service import (
    montar_provas,
    montar_provas_escolhidas,
    sugerir_selecao,
)
from backend.app.services.provas.verificacao import Verificacao
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)
from backend.tests.travamento import espiar_lock

F, M, D = FaixaDificuldade.FACIL, FaixaDificuldade.MEDIA, FaixaDificuldade.DIFICIL


def banco_congelado(db, docente, sessao, objetivas=(7, 10, 8), discursivas=(0, 0, 0)):
    """Congela pelo serviço do controle do banco: banco CONGELADO sem relatório de
    congelamento é incoerente, e a montagem recusa."""
    banco = criar_banco(
        db,
        sessao,
        n_objetivas=sum(objetivas),
        n_discursivas=sum(discursivas),
    )
    numero = 0
    for faixa, quantas in zip((F, M, D), objetivas, strict=True):
        for _ in range(quantas):
            numero += 1
            criar_questao_objetiva(
                db, banco, numero=numero, faixa=faixa, subtema=f"obj{numero}"
            )
    for faixa, quantas in zip((F, M, D), discursivas, strict=True):
        for _ in range(quantas):
            numero += 1
            criar_questao_discursiva(
                db, banco, numero=numero, faixa=faixa, subtema=f"disc{numero}"
            )
    db.commit()
    congelar_banco(db, docente, banco, banco.revisao)
    return banco


def test_monta_as_duas_provas(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    resultado = montar_provas(db_session, docente, banco, 10, 0, banco.revisao)

    assert resultado.verificacao.violacoes == []
    assert resultado.revisao_banco == banco.revisao
    provas = db_session.query(Prova).order_by(Prova.versao).all()
    assert [p.versao for p in provas] == ["A", "B"]
    assert all(p.estado is EstadoProva.MONTADA for p in provas)
    assert all(p.n_questoes == 10 for p in provas)
    assert db_session.query(ItemProva).count() == 20
    assert sessao_rascunho.estado is EstadoSessao.PROVAS_MONTADAS


def test_discursiva_nao_recebe_letra_nem_ordem(db_session, docente, sessao_rascunho):
    banco = banco_congelado(
        db_session, docente, sessao_rascunho, objetivas=(6, 8, 6), discursivas=(2, 3, 2)
    )
    montar_provas(db_session, docente, banco, 7, 3, banco.revisao)
    itens = db_session.query(ItemProva).all()
    discursivos = [i for i in itens if not i.questao.alternativas]
    assert discursivos
    assert all(
        i.letra_atribuida is None and i.ordem_alternativas is None for i in discursivos
    )


def test_mesma_questao_tem_ordens_diferentes_em_a_e_em_b(
    db_session, docente, sessao_rascunho
):
    """Se os distratores ficassem na mesma ordem, comparar as duas versões
    entregaria a resposta."""
    banco = banco_congelado(db_session, docente, sessao_rascunho, objetivas=(7, 10, 5))
    resultado = montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    assert resultado.compartilhadas, "este banco força compartilhamento"
    numero = resultado.compartilhadas[0]
    ordens = {
        item.prova.versao: item.ordem_alternativas
        for item in db_session.query(ItemProva).all()
        if item.questao.numero == numero
    }
    assert ordens["A"] != ordens["B"]


def test_banco_aberto_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    banco.estado = EstadoBanco.ABERTO
    db_session.commit()
    with pytest.raises(BancoNaoCongeladoException):
        montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    assert db_session.query(Prova).count() == 0


def test_revisao_desatualizada_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    with pytest.raises(RevisaoDesatualizadaException):
        montar_provas(db_session, docente, banco, 10, 0, banco.revisao + 5)
    assert db_session.query(Prova).count() == 0


def test_banco_incoerente_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    banco.n_atual = 99
    db_session.commit()
    with pytest.raises(InconsistenciaDeEstadoException):
        montar_provas(db_session, docente, banco, 10, 0, banco.revisao)


def test_montar_duas_vezes_responde_409(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    with pytest.raises(ProvasJaMontadasException):
        montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    assert db_session.query(Prova).count() == 2


def test_montagem_e_determinista(db_session, docente, sessao_rascunho):
    """Mesma sessão, mesmo banco, mesma revisão: mesmo plano e mesma seleção."""
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    primeiro = [
        (i.prova.versao, i.posicao, i.questao.numero, i.letra_atribuida)
        for i in db_session.query(ItemProva).all()
    ]

    db_session.query(ItemProva).delete()
    db_session.query(Prova).delete()
    sessao_rascunho.estado = EstadoSessao.BANCO_CONGELADO
    db_session.commit()

    montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    segundo = [
        (i.prova.versao, i.posicao, i.questao.numero, i.letra_atribuida)
        for i in db_session.query(ItemProva).all()
    ]
    assert sorted(primeiro) == sorted(segundo)


def test_falha_na_verificacao_nao_deixa_prova_nenhuma(
    db_session, docente, sessao_rascunho, monkeypatch
):
    """Nenhuma prova existe sem a outra — verificado por contagem depois
    de falha forçada no meio, com A e B já gravadas na transação."""
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    monkeypatch.setattr(
        montagem_service,
        "verificar_provas",
        lambda *_a, **_k: Verificacao(["forçada"], 0, 0, 0, {}),
    )
    with pytest.raises(MontagemInconsistenteException):
        montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    assert db_session.query(Prova).count() == 0
    assert db_session.query(ItemProva).count() == 0
    assert sessao_rascunho.estado is not EstadoSessao.PROVAS_MONTADAS


def test_montar_segura_o_lock_da_linha_do_banco(
    db_session, docente, sessao_rascunho, engine, monkeypatch
):
    """Achado 8: sem o lock, duas montagens concorrentes passam juntas pela
    checagem "já existem provas" e a segunda estoura em IntegrityError (500)."""
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    achados = espiar_lock(
        monkeypatch, montagem_service, "verificar_consistencia", engine, banco.id
    )

    montar_provas(db_session, docente, banco, 10, 0, banco.revisao)

    assert achados == [False]


def test_leitura_da_prova_nao_faz_uma_consulta_por_item(
    db_session, docente, sessao_rascunho
):
    from backend.app.services.provas.leitura import ler_prova
    from backend.tests.contagem_queries import contar_queries

    banco = banco_congelado(db_session, docente, sessao_rascunho)
    montadas = montar_provas(db_session, docente, banco, 10, 0, banco.revisao)

    with contar_queries(db_session) as consultas:
        prova = ler_prova(db_session, docente, montadas.prova_a_id)

    assert len(prova.itens) == 10
    assert len(consultas) <= 8, f"{len(consultas)} SELECTs para 10 itens"


def test_provas_do_banco_nao_faz_uma_consulta_por_item(
    db_session, docente, sessao_rascunho
):
    from backend.app.services.provas.leitura import provas_do_banco
    from backend.tests.contagem_queries import contar_queries

    banco = banco_congelado(db_session, docente, sessao_rascunho)
    montar_provas(db_session, docente, banco, 10, 0, banco.revisao)

    with contar_queries(db_session) as consultas:
        provas_do_banco(db_session, banco)

    assert len(consultas) <= 12, f"{len(consultas)} SELECTs para 20 itens"


def test_ler_prova_traz_o_contexto_gravado(db_session, docente, sessao_rascunho):
    from backend.app.services.provas.leitura import ler_prova

    banco = banco_congelado(db_session, docente, sessao_rascunho)
    for questao in banco.questoes:
        if questao.numero % 2:
            questao.justificativa.estrutura_formato = {
                "contexto": f"Cenário {questao.numero}."
            }
    db_session.commit()
    montadas = montar_provas(db_session, docente, banco, 10, 0, banco.revisao)

    prova = ler_prova(db_session, docente, montadas.prova_a_id)

    for item in prova.itens:
        esperado = f"Cenário {item.numero}." if item.numero % 2 else None
        assert item.contexto == esperado


def _numeros(db, versao):
    prova = db.query(Prova).filter_by(versao=versao).one()
    return sorted(item.questao.numero for item in prova.itens)


def test_escolha_do_docente_vai_exatamente_para_cada_prova(
    db_session, docente, sessao_rascunho
):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    a, b = list(range(1, 11)), list(range(11, 21))

    resultado = montar_provas_escolhidas(db_session, docente, banco, a, b, banco.revisao)

    assert resultado.verificacao.violacoes == []
    assert resultado.compartilhadas == []
    assert _numeros(db_session, "A") == a
    assert _numeros(db_session, "B") == b
    assert sessao_rascunho.estado is EstadoSessao.PROVAS_MONTADAS


def test_escolha_pode_por_a_mesma_questao_nas_duas(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)

    resultado = montar_provas_escolhidas(
        db_session, docente, banco, list(range(1, 11)), list(range(6, 16)), banco.revisao
    )

    assert resultado.compartilhadas == [6, 7, 8, 9, 10]
    assert resultado.verificacao.violacoes == []


def test_escolha_nao_exige_a_proporcao_de_faixas(db_session, docente, sessao_rascunho):
    """A proporção fácil/média/difícil vale na geração do banco; na montagem
    quem decide é o docente."""
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    faceis, dificeis = list(range(1, 8)), list(range(18, 26))

    resultado = montar_provas_escolhidas(
        db_session, docente, banco, faceis, dificeis, banco.revisao
    )

    assert resultado.verificacao.violacoes == []


def test_escolha_com_questao_fora_do_banco_ativo_e_recusada(
    db_session, docente, sessao_rascunho
):
    banco = banco_congelado(db_session, docente, sessao_rascunho)

    with pytest.raises(QuestoesIndisponiveisException) as erro:
        montar_provas_escolhidas(db_session, docente, banco, [1, 99], [2], banco.revisao)
    assert erro.value.extras["numeros"] == [99]
    assert db_session.query(Prova).count() == 0


def test_escolha_respeita_o_limite_de_subtema_em_comum(
    db_session, docente, sessao_rascunho
):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    for questao in banco.questoes:
        if questao.numero in (1, 2, 3):
            questao.subtema = "grafos"
    db_session.commit()

    with pytest.raises(SobreposicaoInevitavelException):
        montar_provas_escolhidas(
            db_session, docente, banco, [1, 2, 3, 4], [1, 2, 3, 5], banco.revisao
        )
    assert db_session.query(Prova).count() == 0


def test_sugestao_e_a_selecao_automatica_e_nao_grava_nada(
    db_session, docente, sessao_rascunho
):
    banco = banco_congelado(db_session, docente, sessao_rascunho)

    sugestao = sugerir_selecao(db_session, banco, 10, 0)

    assert db_session.query(Prova).count() == 0
    montar_provas(db_session, docente, banco, 10, 0, banco.revisao)
    assert sorted(q.numero for q in sugestao.a) == _numeros(db_session, "A")
    assert sorted(q.numero for q in sugestao.b) == _numeros(db_session, "B")
