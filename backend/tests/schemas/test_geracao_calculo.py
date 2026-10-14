import pytest
from pydantic import ValidationError

from backend.app.schemas.geracao import montar_schema_calculo


def _questao(k, **mudancas):
    base = {
        "tipo": "questao",
        "contexto": "Um objeto cai.",
        "comando": "Calcule a velocidade.",
        "dados": [{"simbolo": "h", "valor": 5.0, "unidade": "m"}],
        "formula_citada": "v = sqrt(2 g h)",
        "expressao": "sqrt(2 * 9.8 * h)",
        "unidade_resultado": "m/s",
        "erros": [{"descricao": f"erro {i}", "expressao": "h"} for i in range(k - 1)],
        "objetivo_cognitivo": "aplicar",
        "fontes": [
            {"identificador_material": "P1", "localizacao": "p. 1", "trecho_base": "x"}
        ],
        "tema": "t",
        "subtema": "s",
        "nivel_bloom": "aplicar",
    }
    return {"resultado": {**base, **mudancas}}


def test_aceita_k_menos_um_erros():
    montar_schema_calculo(4).model_validate(_questao(4))


@pytest.mark.parametrize("n_erros", [0, 2, 4])
def test_recusa_numero_errado_de_erros(n_erros):
    corpo = _questao(4, erros=[{"descricao": "d", "expressao": "h"}] * n_erros)
    with pytest.raises(ValidationError):
        montar_schema_calculo(4).model_validate(corpo)


def test_dados_exige_ao_menos_um():
    with pytest.raises(ValidationError):
        montar_schema_calculo(3).model_validate(_questao(3, dados=[]))


def test_insuficiencia_continua_valida():
    montar_schema_calculo(3).model_validate(
        {
            "resultado": {
                "tipo": "insuficiencia_de_fonte",
                "informacao_faltante": "a fórmula",
            }
        }
    )
