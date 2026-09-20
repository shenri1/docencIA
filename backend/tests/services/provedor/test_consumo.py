from decimal import Decimal

from backend.app.domain import TipoProvedorLLM
from backend.app.models.prompt_provedor import ProvedorLLM
from backend.app.services.provedor.consumo import (
    RegistradorConsumoFake,
    calcular_custo,
)
from backend.app.services.provedor.tipos import UsoTokens


def provedor(entrada: str, saida: str) -> ProvedorLLM:
    """Objeto ORM não anexado a sessão: `calcular_custo` é função pura.

    Só os campos que ele lê são preenchidos. Construir o objeto inteiro aqui
    amarraria esta task às colunas que a Task 3 ainda vai criar.
    """
    return ProvedorLLM(
        id=1,
        nome="teste",
        tipo=TipoProvedorLLM.LOCAL,
        preco_input_por_milhao=Decimal(entrada),
        preco_output_por_milhao=Decimal(saida),
    )


def test_provedor_local_com_preco_zero_custa_zero():
    custo = calcular_custo(UsoTokens(entrada=1000, saida=500), provedor("0", "0"))
    assert custo == Decimal(0)


def test_custo_usa_preco_por_milhao_de_tokens():
    # 1.000.000 de entrada a 0,15 + 1.000.000 de saída a 0,60
    custo = calcular_custo(
        UsoTokens(entrada=1_000_000, saida=1_000_000), provedor("0.15", "0.60")
    )
    assert custo == Decimal("0.750000")


def test_custo_fracionario_respeita_as_seis_casas_do_banco():
    # A coluna é Numeric(12, 6): quantizar aqui evita erro de arredondamento
    # só na hora do INSERT.
    custo = calcular_custo(UsoTokens(entrada=1, saida=0), provedor("0.15", "0.60"))
    assert custo == Decimal("0.000000")
    assert custo.as_tuple().exponent == -6


def test_custo_e_decimal_e_nunca_float():
    custo = calcular_custo(UsoTokens(entrada=10, saida=10), provedor("1", "1"))
    assert isinstance(custo, Decimal)
    assert not isinstance(custo, float)


def test_fake_guarda_o_que_foi_registrado():
    registrador = RegistradorConsumoFake()
    uso = UsoTokens(entrada=10, saida=20)
    registrador.registrar(sessao_id=7, provedor=provedor("0", "0"), uso=uso)
    assert registrador.registros == [(7, 1, uso)]


def test_requisicao_aceita_modelo_pydantic_como_formato():
    from pydantic import BaseModel

    from backend.app.services.provedor.tipos import RequisicaoLLM

    class Saida(BaseModel):
        enunciado: str

    req = RequisicaoLLM(sistema="s", usuario="u", formato=Saida)
    assert (
        req.formato.model_json_schema()["properties"]["enunciado"]["type"] == "string"
    )
    assert req.temperatura is None
    assert req.max_tokens is None


def test_config_llm_vem_das_settings():
    from backend.app.services.provedor.tipos import ConfigLLM

    cfg = ConfigLLM.das_settings()
    assert cfg.num_ctx == 8192
    assert cfg.base_url == "http://localhost:11434"
