import pytest

from backend.app.domain import FaixaDificuldade
from backend.app.exceptions import (
    BancoInsuficienteParaProvaException,
    SobreposicaoInevitavelException,
)
from backend.app.services.provas.selecao import selecionar
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)

F, M, D = FaixaDificuldade.FACIL, FaixaDificuldade.MEDIA, FaixaDificuldade.DIFICIL


def montar(db, sessao, objetivas: dict, discursivas: dict | None = None):
    """`objetivas` e `discursivas` são {faixa: [subtema, ...]} — o subtema de
    cada questão é explícito, porque é o que a regra de sobreposição compara."""
    total = sum(len(v) for v in objetivas.values()) + sum(
        len(v) for v in (discursivas or {}).values()
    )
    banco = criar_banco(
        db,
        sessao,
        n_objetivas=sum(len(v) for v in objetivas.values()),
        n_discursivas=sum(len(v) for v in (discursivas or {}).values()),
    )
    numero = 0
    for faixa, subtemas in objetivas.items():
        for subtema in subtemas:
            numero += 1
            criar_questao_objetiva(
                db, banco, numero=numero, faixa=faixa, subtema=subtema
            )
    for faixa, subtemas in (discursivas or {}).items():
        for subtema in subtemas:
            numero += 1
            criar_questao_discursiva(
                db, banco, numero=numero, faixa=faixa, subtema=subtema
            )
    db.commit()
    assert len(banco.questoes) == total
    return banco


def subtemas(n: int, prefixo: str = "s") -> list[str]:
    return [f"{prefixo}{i}" for i in range(n)]


def test_banco_folgado_da_provas_disjuntas(db_session, sessao_rascunho):
    """Banco de 25 com 30/40/30 tem 7/10/8; duas provas de 10 precisam 6/8/6.
    Cabe disjunto, e aí nenhuma questão está "em ambas"."""
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: subtemas(8, "d")},
    )
    selecao = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")

    assert len(selecao.a) == len(selecao.b) == 10
    assert selecao.compartilhadas == []
    assert {q.id for q in selecao.a} & {q.id for q in selecao.b} == set()


def test_prova_respeita_a_distribuicao_por_faixa(db_session, sessao_rascunho):
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: subtemas(8, "d")},
    )
    selecao = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")
    for prova in (selecao.a, selecao.b):
        contagem = {faixa: 0 for faixa in (F, M, D)}
        for questao in prova:
            contagem[questao.faixa_dificuldade] += 1
        assert contagem == {F: 3, M: 4, D: 3}


def test_banco_desequilibrado_forca_compartilhamento(db_session, sessao_rascunho):
    """O caso NORMAL depois de âncora improdutiva: banco 7/10/4 pedindo 6/8/6.
    Faltam 2 difíceis, e a sobreposição é a válvula de escape."""
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: subtemas(4, "d")},
    )
    selecao = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")

    assert len(selecao.a) == len(selecao.b) == 10
    assert len(selecao.compartilhadas) == 2


def test_compartilha_o_minimo_necessario(db_session, sessao_rascunho):
    """Nunca mais do que a faixa obriga."""
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: subtemas(5, "d")},
    )
    selecao = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")
    assert len(selecao.compartilhadas) == 1


def test_banco_insuficiente_levanta_com_a_tabela(db_session, sessao_rascunho):
    """Uma prova só já não cabe: 2 difíceis para uma cota de 3."""
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: subtemas(2, "d")},
    )
    with pytest.raises(BancoInsuficienteParaProvaException) as erro:
        selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")
    assert erro.value.extras["cotas_por_faixa"] == {
        "facil": 3,
        "media": 4,
        "dificil": 3,
    }
    assert erro.value.extras["disponivel_por_celula"]["objetiva/dificil"] == 2


def test_subtema_repetido_nas_compartilhadas_levanta(db_session, sessao_rascunho):
    """no máximo 2 questões com o mesmo subtema nas duas provas. Aqui as
    3 difíceis compartilhadas têm todas o mesmo subtema."""
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: ["igual"] * 3},
    )
    with pytest.raises(SobreposicaoInevitavelException) as erro:
        selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")
    assert erro.value.extras["subtema"] == "igual"
    assert erro.value.extras["limite"] == 2


def test_subtema_nulo_nunca_colide(db_session, sessao_rascunho):
    """Banco gerado antes tem subtema NULL em tudo. A prova sai, e a
    contagem de `sem_subtema` diz que a verificação foi parcial."""
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: [None] * 7, M: [None] * 10, D: [None] * 4},
    )
    selecao = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="x")
    assert len(selecao.compartilhadas) == 2
    assert selecao.sem_subtema == 18


def test_banco_misto_respeita_as_contagens_por_tipo(db_session, sessao_rascunho):
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(6, "f"), M: subtemas(8, "m"), D: subtemas(6, "d")},
        {F: subtemas(2, "df"), M: subtemas(3, "dm"), D: subtemas(2, "dd")},
    )
    selecao = selecionar(banco.questoes, 7, 3, 30, 40, 30, semente="x")
    for prova in (selecao.a, selecao.b):
        assert len(prova) == 10
        objetivas = sum(1 for q in prova if q.alternativas)
        assert objetivas == 7


def test_mesma_semente_mesma_selecao(db_session, sessao_rascunho):
    banco = montar(
        db_session,
        sessao_rascunho,
        {F: subtemas(7, "f"), M: subtemas(10, "m"), D: subtemas(8, "d")},
    )
    um = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="igual")
    dois = selecionar(banco.questoes, 10, 0, 30, 40, 30, semente="igual")
    assert [q.id for q in um.a] == [q.id for q in dois.a]
    assert [q.id for q in um.b] == [q.id for q in dois.b]
