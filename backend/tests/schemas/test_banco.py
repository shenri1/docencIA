import pytest
from pydantic import ValidationError

from backend.app.schemas.banco import N_MAXIMO_BANCO, ExclusaoCriar
from backend.app.schemas.orquestrador import ComandoExcluir


def test_exclusao_aceita_ate_o_tamanho_maximo_do_banco():
    dados = ExclusaoCriar(
        numeros=list(range(1, N_MAXIMO_BANCO + 1)), revisao_esperada=0
    )
    assert len(dados.numeros) == N_MAXIMO_BANCO


def test_exclusao_recusa_lista_maior_que_o_banco():
    with pytest.raises(ValidationError):
        ExclusaoCriar(numeros=list(range(N_MAXIMO_BANCO + 1)), revisao_esperada=0)


def test_comando_excluir_do_orquestrador_recusa_lista_maior_que_o_banco():
    with pytest.raises(ValidationError):
        ComandoExcluir(
            comando="excluir",
            versao="v1",
            revisao_esperada=0,
            numeros=list(range(N_MAXIMO_BANCO + 1)),
        )
