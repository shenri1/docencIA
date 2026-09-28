from backend.app.domain import EstadoProva, FaixaDificuldade
from backend.app.models.provas import ItemProva, Prova
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.provas.verificacao import verificar_provas
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva


def par_de_provas(db, sessao, letras_a: str, letras_b: str, subtemas=None):
    """Duas provas com uma questão objetiva por posição. `letras_a` e `letras_b`
    são as letras atribuídas; questões compartilhadas são as de mesmo índice
    quando `subtemas` repete."""
    n = len(letras_a)
    subtemas = subtemas or [f"s{i}" for i in range(2 * n)]
    banco = criar_banco(db, sessao, n_objetivas=2 * n)
    # Faixas conforme a distribuição da sessão, para a checagem de composição
    # por faixa não acusar o par coerente.
    faixas = [
        faixa
        for faixa, quantas in calcular_distribuicao(
            n, sessao.p_f, sessao.p_m, sessao.p_d
        ).itens()
        for _ in range(quantas)
    ]
    questoes = [
        criar_questao_objetiva(
            db, banco, numero=i + 1, subtema=subtemas[i], faixa=faixas[i % n]
        )
        for i in range(2 * n)
    ]
    db.commit()
    provas = []
    for versao, letras, fatia in (
        ("A", letras_a, questoes[:n]),
        ("B", letras_b, questoes[n:]),
    ):
        prova = Prova(
            sessao_id=sessao.id,
            banco_id=banco.id,
            versao=versao,
            n_questoes=n,
            n_objetivas=n,
            n_discursivas=0,
            revisao_banco=banco.revisao,
            estado=EstadoProva.MONTADA,
        )
        db.add(prova)
        db.flush()
        for posicao, (letra, questao) in enumerate(
            zip(letras, fatia, strict=True), start=1
        ):
            original = sorted(a.letra for a in questao.alternativas)
            correta = next(a.letra for a in questao.alternativas if a.correta)
            ordem = original[:]
            # Coloca a correta na posição da letra atribuída.
            destino = original.index(letra)
            ordem[original.index(correta)], ordem[destino] = (
                ordem[destino],
                ordem[original.index(correta)],
            )
            db.add(
                ItemProva(
                    prova_id=prova.id,
                    questao_id=questao.id,
                    posicao=posicao,
                    letra_atribuida=letra,
                    ordem_alternativas=ordem,
                )
            )
        provas.append(prova)
    db.commit()
    return banco, provas[0], provas[1]


def test_par_coerente_nao_tem_violacao(db_session, sessao_rascunho):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "CCBDDEABAE", "BAEDECCDBA")
    resultado = verificar_provas(db_session, a, b)
    assert resultado.violacoes == []


def test_contagem_desequilibrada_de_letras_e_violacao(db_session, sessao_rascunho):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "ABACADAEAB", "BAEDECCDBA")
    violacoes = verificar_provas(db_session, a, b).violacoes
    assert any("diferença" in v or "contagem" in v for v in violacoes)


def test_progressao_aritmetica_e_violacao(db_session, sessao_rascunho):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "ABCDEBADCE", "BAEDECCDBA")
    assert any("progressão" in v for v in verificar_provas(db_session, a, b).violacoes)


def test_deriva_monotona_e_violacao(db_session, sessao_rascunho):
    """O furo que os três primeiros filtros deixavam passar, agora acusado pela
    verificação — sem isto, o critério de aceitação seria mentira."""
    _, a, b = par_de_provas(db_session, sessao_rascunho, "AABBCCDDEE", "BAEDECCDBA")
    assert any("monótona" in v for v in verificar_provas(db_session, a, b).violacoes)


def test_periodo_curto_e_violacao(db_session, sessao_rascunho):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "ABDABDABDA", "BAEDECCDBA")
    assert any("período" in v for v in verificar_provas(db_session, a, b).violacoes)


def test_colisao_acima_da_metade_e_violacao(db_session, sessao_rascunho):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "CCBDDEABAE", "CCBDDEABAE")
    resultado = verificar_provas(db_session, a, b)
    assert resultado.colisoes_letras == 10
    assert any("colis" in v for v in resultado.violacoes)


def test_subtema_repetido_entre_compartilhadas_e_violacao(db_session, sessao_rascunho):
    """Três questões do mesmo subtema nas duas provas: acima do limite de 2."""
    _, a, b = par_de_provas(db_session, sessao_rascunho, "ABDCE", "CEBAD")
    # Reaponta os três primeiros itens de B para as questões de A.
    itens_a = sorted(a.itens, key=lambda i: i.posicao)
    itens_b = sorted(b.itens, key=lambda i: i.posicao)
    for item_b, item_a in zip(itens_b[:3], itens_a[:3], strict=True):
        item_b.questao_id = item_a.questao_id
        item_a.questao.subtema = "igual"
    db_session.commit()
    resultado = verificar_provas(db_session, a, b)
    assert resultado.compartilhadas == 3
    assert resultado.subtemas_compartilhados["igual"] == 3
    assert any("subtema" in v for v in resultado.violacoes)


def test_ordem_alternativas_que_nao_e_permutacao_e_violacao(
    db_session, sessao_rascunho
):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "ABDCE", "CEBAD")
    item = min(a.itens, key=lambda i: i.posicao)
    item.ordem_alternativas = ["A", "A", "B", "C", "D"]
    db_session.commit()
    assert any("permutação" in v for v in verificar_provas(db_session, a, b).violacoes)


def test_correta_fora_da_letra_atribuida_e_violacao(db_session, sessao_rascunho):
    _, a, b = par_de_provas(db_session, sessao_rascunho, "ABDCE", "CEBAD")
    item = min(a.itens, key=lambda i: i.posicao)
    item.ordem_alternativas = list(reversed(item.ordem_alternativas))
    db_session.commit()
    assert any("correta" in v for v in verificar_provas(db_session, a, b).violacoes)


def test_revisao_divergente_e_violacao(db_session, sessao_rascunho):
    banco, a, b = par_de_provas(db_session, sessao_rascunho, "ABDCE", "CEBAD")
    banco.revisao += 1
    db_session.commit()
    assert any("revis" in v for v in verificar_provas(db_session, a, b).violacoes)


def test_varias_violacoes_saem_juntas(db_session, sessao_rascunho):
    """Todas as checagens rodam antes de devolver: quem monta vê a lista inteira."""
    banco, a, b = par_de_provas(db_session, sessao_rascunho, "AABBCCDDEE", "AABBCCDDEE")
    banco.revisao += 1
    db_session.commit()
    assert len(verificar_provas(db_session, a, b).violacoes) >= 3


def test_contagem_por_faixa_divergente_e_violacao(db_session, sessao_rascunho):
    """Checagem 9: as contagens por faixa batem com a distribuição pedida."""
    _, a, b = par_de_provas(db_session, sessao_rascunho, "CCBDDEABAE", "BAEDECCDBA")
    item = min(a.itens, key=lambda i: i.posicao)
    item.questao.faixa_dificuldade = FaixaDificuldade.DIFICIL
    db_session.commit()
    assert any("faixa" in v for v in verificar_provas(db_session, a, b).violacoes)
