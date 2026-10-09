from backend.app.core.config import settings
from backend.app.domain import FaixaDificuldade, RegraQualidade, TipoQuestao
from backend.app.prompt.montagem import montar_sistema_critico
from backend.app.schemas.geracao import montar_schema_discursiva, montar_schema_objetiva
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.critico.agente_critico_service import (
    item_discursivo_de,
    item_objetivo_de,
    revisar_questao,
)
from backend.app.services.geracao.contexto import parametros_da_sessao
from backend.app.services.geracao.formatos import montar_discursiva, montar_proposicao
from backend.app.services.qualidade.validador_itens import Violacao
from backend.app.services.rag.retrieval_service import TrechoRecuperado
from backend.tests.services.geracao.duplos import (
    ProvedorLLMFake,
    corpo_discursiva,
    corpo_insuficiencia,
    corpo_questao,
)

DISTRIBUICAO = calcular_distribuicao(10, 30, 40, 30)
TRECHOS = [
    TrechoRecuperado(7, "P1", "página 12", "A busca em largura usa uma fila.", 0.9, 0.8)
]
VIOLACAO = Violacao(
    RegraQualidade.TAMANHO_ALTERNATIVA, "C", "C tem 14 palavras; média das demais = 5,5"
)


def rascunho(k: int = 5, **sobrescritas):
    return montar_schema_objetiva(k).model_validate(corpo_questao(k, **sobrescritas)).resultado


def revisar(provedor, sessao, violacoes=(VIOLACAO,)):
    return revisar_questao(
        provedor,
        sessao,
        TRECHOS,
        rascunho(),
        list(violacoes),
        FaixaDificuldade.MEDIA,
        DISTRIBUICAO,
    )


def test_mensagem_leva_trechos_rascunho_e_violacoes(sessao_rascunho):
    provedor = ProvedorLLMFake([corpo_questao(5)])
    revisar(provedor, sessao_rascunho)
    usuario = provedor.requisicoes[0].usuario
    assert "[P1, página 12] A busca em largura usa uma fila." in usuario
    assert '"comando"' in usuario
    assert "tamanho_alternativa" in usuario
    assert "C tem 14 palavras; média das demais = 5,5" in usuario
    assert "media" in usuario
    assert "exatamente 5 alternativas" in usuario


def test_sem_violacoes_a_mensagem_diz_isso(sessao_rascunho):
    provedor = ProvedorLLMFake([corpo_questao(5)])
    revisar(provedor, sessao_rascunho, violacoes=())
    assert "Nenhuma violação de forma" in provedor.requisicoes[0].usuario


def test_usa_o_prompt_do_critico_e_os_parametros_do_critico(sessao_rascunho):
    provedor = ProvedorLLMFake([corpo_questao(5)])
    revisar(provedor, sessao_rascunho)
    requisicao = provedor.requisicoes[0]
    assert requisicao.sistema == montar_sistema_critico(
        TipoQuestao.OBJETIVA, parametros_da_sessao(sessao_rascunho, DISTRIBUICAO)
    )
    assert requisicao.temperatura == settings.critico_temperatura
    assert requisicao.max_tokens == settings.critico_max_tokens


def test_questao_revisada_volta(sessao_rascunho):
    provedor = ProvedorLLMFake([corpo_questao(5, enunciado="Versão revisada?")])
    resultado = revisar(provedor, sessao_rascunho)
    assert resultado.questao.comando == "Versão revisada?"
    assert resultado.motivo_insuficiencia is None
    assert resultado.modelo == "fake"


def test_insuficiencia_declarada_pelo_critico(sessao_rascunho):
    provedor = ProvedorLLMFake([corpo_insuficiencia("o trecho não define o critério")])
    resultado = revisar(provedor, sessao_rascunho)
    assert resultado.questao is None
    assert "critério" in resultado.motivo_insuficiencia


def test_item_de_atribui_letra_por_posicao_e_correta_pela_letra():
    item = item_objetivo_de(montar_proposicao(rascunho(letra_correta="C")), TRECHOS)
    assert [a.letra for a in item.alternativas] == ["A", "B", "C", "D", "E"]
    assert [a.letra for a in item.alternativas if a.correta] == ["C"]
    assert [a.letra for a in item.alternativas if a.e_gemeo_malvado] == ["B"]
    assert item.trechos_base == ["A busca em largura usa uma fila."]
    assert item.identificadores_fonte == ["P1"]


def rascunho_discursivo(**sobrescritas):
    return montar_schema_discursiva().model_validate(
        corpo_discursiva(**sobrescritas)
    ).resultado


def test_revisao_discursiva_usa_sistema_e_pedido_proprios(sessao_rascunho):
    provedor = ProvedorLLMFake([corpo_discursiva()])
    resultado = revisar_questao(
        provedor,
        sessao_rascunho,
        TRECHOS,
        rascunho_discursivo(),
        [],
        FaixaDificuldade.DIFICIL,
        DISTRIBUICAO,
        tipo=TipoQuestao.DISCURSIVA,
    )
    requisicao = provedor.requisicoes[0]
    assert "<revisao_discursiva>" in requisicao.sistema
    assert "<revisao_objetiva>" not in requisicao.sistema
    assert "2 a 5 aspectos esperados" in requisicao.usuario
    assert '"aspectos_esperados"' in requisicao.usuario
    assert len(resultado.questao.aspectos_esperados) == 2


def test_item_discursivo_de_leva_o_trecho_de_cada_aspecto():
    item = item_discursivo_de(montar_discursiva(rascunho_discursivo()), TRECHOS)
    assert item.enunciado.startswith("Explique")
    assert [a.trecho_base for a in item.aspectos] == [
        "A busca em largura usa uma fila."
    ] * 2
    assert item.identificadores_fonte == ["P1"]


def test_item_objetivo_de_leva_justificativa_e_invalidacoes():
    from backend.app.schemas.geracao import montar_schema_objetiva
    from backend.app.services.critico.agente_critico_service import item_objetivo_de
    from backend.tests.services.geracao.duplos import corpo_questao

    questao = montar_schema_objetiva(5).model_validate(corpo_questao(5)).resultado
    item = item_objetivo_de(montar_proposicao(questao), [])
    assert item.justificativa_correta == "o trecho afirma o uso de fila"
    assert item.texto_verificacao_unicidade == "nenhuma errada é defensável"
    assert item.invalidacoes == [
        ("B", "distrator 1"),
        ("C", "distrator 2"),
        ("D", "distrator 3"),
        ("E", "distrator 4"),
    ]
