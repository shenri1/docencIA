from backend.app.domain import FaixaDificuldade, TipoGabarito
from backend.app.models.banco import (
    Alternativa,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
)
from backend.app.models.provas import ItemProva, Prova
from backend.app.services.controle_banco.exclusao_service import congelar_banco
from backend.app.services.provas.gabarito import gerar_gabarito
from backend.app.services.provas.montagem_service import montar_provas
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)

F, M, D = FaixaDificuldade.FACIL, FaixaDificuldade.MEDIA, FaixaDificuldade.DIFICIL
SIMPLES, COMENTADO = TipoGabarito.SIMPLES, TipoGabarito.COMENTADO


def provas_montadas(db, docente, sessao, discursivas=0, **fabrica):
    """Banco congelado 7/10/8 de objetivas (+ discursivas médias opcionais) e as
    duas provas montadas. `fabrica` vai para criar_questao_objetiva."""
    banco = criar_banco(db, sessao, n_objetivas=25, n_discursivas=discursivas)
    numero = 0
    for faixa, quantas in ((F, 7), (M, 10), (D, 8)):
        for _ in range(quantas):
            numero += 1
            criar_questao_objetiva(
                db, banco, numero=numero, faixa=faixa, subtema=f"s{numero}", **fabrica
            )
    for _ in range(discursivas):
        numero += 1
        criar_questao_discursiva(
            db, banco, numero=numero, faixa=M, subtema=f"s{numero}"
        )
    db.commit()
    # Pelo serviço da congelar sem relatório de congelamento é estado
    # incoerente, e montar_provas recusa.
    congelar_banco(db, docente, banco, banco.revisao)
    montadas = montar_provas(
        db, docente, banco, 10 - min(discursivas, 3), min(discursivas, 3), banco.revisao
    )
    return banco, montadas


def item_da_prova(db, prova_id, posicao) -> ItemProva:
    return (
        db.query(ItemProva)
        .filter(ItemProva.prova_id == prova_id, ItemProva.posicao == posicao)
        .one()
    )


def test_simples_da_a_letra_da_prova_e_a_fonte(db_session, docente, sessao_rascunho):
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, SIMPLES)

    assert gabarito.completo and gabarito.problemas == []
    assert len(gabarito.itens) == 10
    for item_gab in gabarito.itens:
        item = item_da_prova(db_session, montadas.prova_a_id, item_gab.posicao)
        assert item_gab.letra == item.letra_atribuida
        assert item_gab.fontes[0].localizacao
        assert item_gab.fontes[0].trecho_base is None  # só no comentado
        assert item_gab.justificativa_correta is None
        assert item_gab.invalidacoes == []


def test_letra_do_gabarito_e_a_da_prova_nao_a_original(
    db_session, docente, sessao_rascunho
):
    """Na fábrica a correta original é sempre A. Se o gabarito dissesse A em
    todas as posições, estaria lendo a letra original."""
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, SIMPLES)
    assert {i.letra for i in gabarito.itens} != {"A"}


def test_comentado_liga_cada_motivo_a_letra_da_prova(
    db_session, docente, sessao_rascunho
):
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)

    # Sem estas contagens, um gabarito sem itens ou sem invalidações passaria:
    # os laços abaixo não rodariam.
    assert len(gabarito.itens) == 10
    for item_gab in gabarito.itens:
        item = item_da_prova(db_session, montadas.prova_a_id, item_gab.posicao)
        # A fábrica grava o motivo como "distrator <letra original>".
        originais = {letra: original for original, letra in _mapa(item).items()}
        assert len(item_gab.invalidacoes) == 4  # K = 5: uma por errada
        assert item_gab.invalidacoes_sem_letra is False
        assert [i.letra for i in item_gab.invalidacoes] == sorted(
            i.letra for i in item_gab.invalidacoes
        )
        assert item_gab.letra not in {i.letra for i in item_gab.invalidacoes}
        for invalidacao in item_gab.invalidacoes:
            assert invalidacao.motivo == f"distrator {originais[invalidacao.letra]}"
        assert item_gab.fontes[0].trecho_base
        assert item_gab.justificativa_correta


def _mapa(item):
    from backend.app.services.provas.leitura import letras_na_prova

    return letras_na_prova(item)


def test_banco_antigo_sai_sem_letra_com_aviso(db_session, docente, sessao_rascunho):
    _, montadas = provas_montadas(
        db_session, docente, sessao_rascunho, invalidacoes_ligadas=False
    )
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)
    item_gab = gabarito.itens[0]
    assert item_gab.invalidacoes_sem_letra is True
    assert all(i.letra is None for i in item_gab.invalidacoes)
    assert len(item_gab.invalidacoes) == 4
    assert gabarito.completo  # sem letra não é incompleto: o motivo está lá


def test_letras_invalidas_caem_para_sem_letra(db_session, docente, sessao_rascunho):
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    item = item_da_prova(db_session, montadas.prova_a_id, 1)
    justificativa = item.questao.justificativa
    justificativa.invalidacao_distratores = [
        {"letra": "B", "motivo": "x"},
        {"letra": "B", "motivo": "y"},  # repetida
        {"letra": "D", "motivo": "z"},
        {"letra": "E", "motivo": "w"},
    ]
    db_session.commit()
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)
    assert gabarito.itens[0].invalidacoes_sem_letra is True
    assert [i.motivo for i in gabarito.itens[0].invalidacoes] == ["x", "y", "z", "w"]


def test_texto_que_cita_letra_sai_intacto_e_marcado(
    db_session, docente, sessao_rascunho
):
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    item = item_da_prova(db_session, montadas.prova_a_id, 1)
    item.questao.justificativa.justificativa_correta = "A alternativa B confunde."
    db_session.commit()
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)
    assert gabarito.itens[0].cita_letra is True
    assert gabarito.itens[0].justificativa_correta == "A alternativa B confunde."


def test_simples_nunca_marca_cita_letra(db_session, docente, sessao_rascunho):
    """A simples não mostra texto livre; o aviso não tem a que se referir."""
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    item = item_da_prova(db_session, montadas.prova_a_id, 1)
    item.questao.justificativa.justificativa_correta = "A alternativa B confunde."
    db_session.commit()
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, SIMPLES)
    assert gabarito.itens[0].cita_letra is False


def test_discursiva_tem_aspectos_e_nao_tem_letra(db_session, docente, sessao_rascunho):
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho, discursivas=3)
    simples = gerar_gabarito(db_session, docente, montadas.prova_a_id, SIMPLES)
    comentado = gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)

    discursivos = [i for i in simples.itens if i.aspectos]
    assert len(discursivos) == 3
    assert all(i.letra is None for i in discursivos)
    assert all(a.fonte.trecho_base is None for i in discursivos for a in i.aspectos)

    comentados = [i for i in comentado.itens if i.aspectos]
    # Sem a contagem, um comentado que perdesse os aspectos passaria em branco.
    assert len(comentados) == 3
    assert all(i.objetivo_cognitivo for i in comentados)
    assert all(a.fonte.trecho_base for i in comentados for a in i.aspectos)
    assert simples.completo and comentado.completo


def test_item_sem_fonte_torna_o_gabarito_incompleto(
    db_session, docente, sessao_rascunho
):
    """Critério da 100% das questões. Medido, não suposto."""
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    item = item_da_prova(db_session, montadas.prova_a_id, 3)
    for fonte in list(item.questao.fontes_internas):
        db_session.delete(fonte)
    db_session.commit()
    # expire_on_commit=False: sem isto, a coleção carregada guarda as fontes
    # apagadas.
    db_session.expire_all()
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, SIMPLES)
    assert gabarito.completo is False
    assert any("posição 3" in p for p in gabarito.problemas)


def test_prova_desatualizada_gera_gabarito_marcado(
    db_session, docente, sessao_rascunho
):
    banco, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    banco.revisao += 1
    db_session.commit()
    gabarito = gerar_gabarito(db_session, docente, montadas.prova_a_id, SIMPLES)
    assert gabarito.desatualizada is True
    assert gabarito.completo


def test_gerar_gabarito_nao_escreve_nada(db_session, docente, sessao_rascunho):
    _, montadas = provas_montadas(db_session, docente, sessao_rascunho)
    modelos = (
        Prova,
        ItemProva,
        Questao,
        Alternativa,
        FonteInterna,
        JustificativaEstruturada,
    )
    antes = [db_session.query(m).count() for m in modelos]
    gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)
    assert [db_session.query(m).count() for m in modelos] == antes
    assert not db_session.new and not db_session.dirty


def test_gabarito_da_discursiva_com_itens_leva_o_item(
    db_session, docente, sessao_rascunho
):
    banco, montadas = provas_montadas(
        db_session, docente, sessao_rascunho, discursivas=3
    )
    for questao in banco.questoes:
        for aspecto in questao.aspectos:
            aspecto.item = aspecto.ordem  # 2 aspectos: itens 1 e 2, um cada
    db_session.commit()
    comentado = gerar_gabarito(db_session, docente, montadas.prova_a_id, COMENTADO)
    discursivos = [i for i in comentado.itens if i.aspectos]
    assert discursivos
    assert all([a.item for a in i.aspectos] == [1, 2] for i in discursivos)
