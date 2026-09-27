import pytest

from backend.app.domain import RiscoAuditoria
from backend.app.schemas.auditoria import (
    RISCOS_DO_MODELO,
    montar_schema_auditoria,
)

LOCS = ["página 3", "página 7"]


def _achado(**sobrescritas) -> dict:
    base = {
        "risco": "correta_nao_unica",
        "alvo": "C",
        "localizacao": "página 7",
        "trecho_fonte": "x",
        "proposta_ajuste": "y",
    }
    base.update(sobrescritas)
    return base


def test_achados_pode_vir_vazio():
    """Questão sem problema é o caso comum, não erro."""
    schema = montar_schema_auditoria(5, LOCS)
    assert schema.model_validate({"achados": []}).achados == []


def test_achado_valido_e_aceito():
    schema = montar_schema_auditoria(5, LOCS)
    resultado = schema.model_validate(
        {
            "achados": [
                _achado(
                    trecho_fonte="a busca em largura também percorre por camadas",
                    proposta_ajuste="Reescreva C para não ser sustentável pelo trecho.",
                )
            ]
        }
    )
    assert resultado.achados[0].alvo == "C"


def test_letra_fora_de_k_e_recusada():
    schema = montar_schema_auditoria(3, LOCS)
    with pytest.raises(ValueError):
        schema.model_validate({"achados": [_achado(alvo="E")]})


def test_localizacao_nao_enviada_e_recusada():
    """Citação livre faria a rastreabilidade virar ficção."""
    schema = montar_schema_auditoria(5, LOCS)
    with pytest.raises(ValueError):
        schema.model_validate({"achados": [_achado(localizacao="página 99")]})


def test_modelo_nao_pode_emitir_assimetria_forma():
    """assimetria_forma é medida pelo código; o modelo nunca a emite."""
    schema = montar_schema_auditoria(5, LOCS)
    with pytest.raises(ValueError):
        schema.model_validate({"achados": [_achado(risco="assimetria_forma")]})


def test_riscos_do_modelo_sao_membros_do_enum():
    """Trava contra renomear um valor do enum e esquecer o Literal do schema."""
    valores = {r.value for r in RiscoAuditoria}
    assert set(RISCOS_DO_MODELO) <= valores
    assert RiscoAuditoria.ASSIMETRIA_FORMA.value not in RISCOS_DO_MODELO


def test_localizacoes_repetidas_sao_deduplicadas_na_ordem():
    """Dois chunks da mesma página dariam valor repetido, e Literal exige
    valores distintos."""
    schema = montar_schema_auditoria(5, ["página 3", "página 3", "página 1"])
    achado = schema.model_fields["achados"].annotation.__args__[0]
    enum_localizacao = achado.model_json_schema()["properties"]["localizacao"]["enum"]
    assert enum_localizacao == ["página 3", "página 1"]


def test_k_fora_de_faixa_e_erro_de_programacao():
    with pytest.raises(ValueError, match="k deve estar entre"):
        montar_schema_auditoria(1, LOCS)


def test_localizacoes_vazia_e_erro_de_programacao():
    with pytest.raises(ValueError, match="localizacoes"):
        montar_schema_auditoria(5, [])


def test_json_schema_fecha_alvo_e_localizacao_por_enum():
    """O que a decodificação restrita do Ollama pode impor não deve ser
    conferido depois — lição do nivel_bloom."""
    schema = montar_schema_auditoria(4, LOCS)
    gerado = schema.model_json_schema()
    achado = next(iter(gerado["$defs"].values()))
    assert achado["properties"]["alvo"]["enum"] == ["A", "B", "C", "D"]
    assert achado["properties"]["localizacao"]["enum"] == LOCS
