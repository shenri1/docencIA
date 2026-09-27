from decimal import Decimal

from backend.app.domain import FaixaDificuldade, TipoQuestao
from backend.app.services.controle_banco.relatorio_impacto import calcular_impacto

FACIL, MEDIA, DIFICIL = (
    FaixaDificuldade.FACIL,
    FaixaDificuldade.MEDIA,
    FaixaDificuldade.DIFICIL,
)
OBJ, DISC = TipoQuestao.OBJETIVA, TipoQuestao.DISCURSIVA


def test_distribuicao_exata_nao_desvia_nem_alerta():
    impacto = calcular_impacto(
        {OBJ: {FACIL: 3, MEDIA: 4, DIFICIL: 3}}, {OBJ}, 30, 40, 30
    )
    assert impacto.n_final == 10
    assert impacto.alerta_desvio is False
    tipo = impacto.por_tipo[OBJ]
    assert tipo.n == 10
    assert tipo.desvio_por_faixa == {
        FACIL: Decimal("0.00"),
        MEDIA: Decimal("0.00"),
        DIFICIL: Decimal("0.00"),
    }


def test_fronteira_exata_de_cinco_pontos_nao_alerta():
    """20 questões, pedido 30/40/30, obtido 5/9/6: a fácil desvia exatamente
    -5,00 pontos. |100·5 − 30·20| = 100 = 5·20 — não é MAIOR que, então não
    alerta."""
    impacto = calcular_impacto(
        {OBJ: {FACIL: 5, MEDIA: 9, DIFICIL: 6}}, {OBJ}, 30, 40, 30
    )
    assert impacto.por_tipo[OBJ].desvio_por_faixa[FACIL] == Decimal("-5.00")
    assert impacto.alerta_desvio is False


def test_um_ponto_acima_da_fronteira_alerta():
    """O exemplo: N=10 com 33/33/34 vira 3/3/4 pelo maior resto, e a
    difícil fica +6,00 — o arredondamento sozinho passa de 5 pontos."""
    impacto = calcular_impacto(
        {OBJ: {FACIL: 3, MEDIA: 3, DIFICIL: 4}}, {OBJ}, 33, 33, 34
    )
    assert impacto.por_tipo[OBJ].desvio_por_faixa[DIFICIL] == Decimal("6.00")
    assert impacto.por_tipo[OBJ].alerta_desvio is True
    assert impacto.alerta_desvio is True


def test_faixa_ausente_conta_como_zero():
    impacto = calcular_impacto({OBJ: {MEDIA: 4}}, {OBJ}, 30, 40, 30)
    assert impacto.por_tipo[OBJ].contagem_por_faixa[FACIL] == 0
    assert impacto.por_tipo[OBJ].desvio_por_faixa[FACIL] == Decimal("-30.00")


def test_tipo_pedido_sem_questao_ativa_da_desvio_nulo_e_alerta():
    impacto = calcular_impacto({}, {DISC}, 30, 40, 30)
    tipo = impacto.por_tipo[DISC]
    assert tipo.n == 0
    assert tipo.desvio_por_faixa == {FACIL: None, MEDIA: None, DIFICIL: None}
    assert tipo.alerta_desvio is True
    assert impacto.n_final == 0


def test_tipo_nao_pedido_fica_fora_do_relatorio():
    impacto = calcular_impacto(
        {OBJ: {FACIL: 3, MEDIA: 4, DIFICIL: 3}}, {OBJ}, 30, 40, 30
    )
    assert set(impacto.por_tipo) == {OBJ}


def test_alerta_de_um_tipo_liga_o_alerta_geral():
    impacto = calcular_impacto(
        {OBJ: {FACIL: 3, MEDIA: 4, DIFICIL: 3}, DISC: {FACIL: 5}},
        {OBJ, DISC},
        30,
        40,
        30,
    )
    assert impacto.por_tipo[OBJ].alerta_desvio is False
    assert impacto.por_tipo[DISC].alerta_desvio is True
    assert impacto.alerta_desvio is True
    assert impacto.n_final == 15


def test_quantizacao_usa_round_half_even():
    """100·1/32 = 3,125. Com ROUND_HALF_EVEN dá 3,12; com HALF_UP daria 3,13.
    N=32 não caberia num banco real — aqui a função é pura e o que se testa é
    o arredondamento."""
    impacto = calcular_impacto({OBJ: {FACIL: 1, MEDIA: 31}}, {OBJ}, 0, 100, 0)
    assert impacto.por_tipo[OBJ].desvio_por_faixa[FACIL] == Decimal("3.12")
