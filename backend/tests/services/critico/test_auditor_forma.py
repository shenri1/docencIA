from backend.app.domain import FormatoItem, RiscoAuditoria
from backend.app.models.banco import Alternativa
from backend.app.services.critico.auditor_service import (
    achados_de_forma,
    item_de_questao,
)
from backend.app.services.qualidade.validador_itens import (
    AlternativaAvaliavel,
    ItemObjetivo,
)
from backend.app.services.rag.retrieval_service import TrechoRecuperado
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva

TRECHOS = [
    TrechoRecuperado(
        chunk_id=1,
        material_id=1,
        identificador_curto="P1",
        localizacao="página 3",
        texto="A busca em largura usa uma fila.",
        score=0.9,
        score_vetorial=0.8,
    )
]


def questao_com_textos(db, sessao, textos: list[str], correta: str = "A"):
    """Questão da fábrica com o texto das alternativas reescrito — é assim que
    se monta assimetria sem depender do LLM."""
    banco = criar_banco(db, sessao, n_objetivas=1)
    questao = criar_questao_objetiva(db, banco, numero=1)
    for alternativa in questao.alternativas:
        db.delete(alternativa)
    db.flush()
    for letra, texto in zip("ABCDE", textos, strict=True):
        db.add(
            Alternativa(
                questao_id=questao.id,
                letra=letra,
                texto=texto,
                correta=letra == correta,
                e_gemeo_malvado=letra == "B",
            )
        )
    db.commit()
    db.expire_all()
    return questao


def test_item_de_questao_le_do_orm(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    questao = criar_questao_objetiva(db_session, banco, numero=1)
    db_session.commit()

    item = item_de_questao(questao, TRECHOS)

    assert [a.letra for a in item.alternativas] == ["A", "B", "C", "D", "E"]
    assert [a.correta for a in item.alternativas] == [True, False, False, False, False]
    assert item.enunciado == questao.enunciado
    assert item.trechos_base == [questao.fontes_internas[0].trecho_base]
    # Identificadores vêm dos trechos RECUPERADOS, não das fontes gravadas: é
    # contra eles que a regra de menção de fonte compara.
    assert item.identificadores_fonte == ["P1"]


def test_correta_longa_produz_achado_de_assimetria(db_session, sessao_rascunho):
    questao = questao_com_textos(
        db_session,
        sessao_rascunho,
        [
            (
                "a fila preserva a ordem de descoberta dos vértices e garante "
                "visita por camadas de distância crescente a partir da origem"
            ),
            "pilha",
            "vetor",
            "grafo",
            "arvore",
        ],
    )
    achados = achados_de_forma(item_de_questao(questao, TRECHOS))

    assert [a.risco for a in achados] == [
        RiscoAuditoria.ASSIMETRIA_FORMA,
        RiscoAuditoria.ASSIMETRIA_FORMA,
    ]
    assert {a.alvo for a in achados} == {"A"}
    # Assimetria não é concorrência de fonte.
    assert all(a.localizacao is None and a.trecho_fonte is None for a in achados)
    # A proposta carrega o que foi medido: "risco identificado".
    assert "palavras" in achados[0].proposta_ajuste


def test_questao_equilibrada_nao_produz_achado(db_session, sessao_rascunho):
    questao = questao_com_textos(
        db_session,
        sessao_rascunho,
        ["fila simples", "pilha comum", "vetor fixo", "grafo denso", "arvore rasa"],
    )
    assert achados_de_forma(item_de_questao(questao, TRECHOS)) == []


def test_regras_de_rf020_nao_entram_no_relatorio(db_session, sessao_rascunho):
    """`termo_absoluto` e `mencao_fonte` sã e já apareceram na geração.
    Repeti-las aqui poluiria o relatório com outro requisito."""
    questao = questao_com_textos(
        db_session,
        sessao_rascunho,
        [
            "sempre uma fila",  # termo_absoluto
            "segundo o slide, pilha",  # mencao_fonte
            "vetor fixo simples",
            "grafo denso comum",
            "arvore rasa binária",
        ],
    )
    assert achados_de_forma(item_de_questao(questao, TRECHOS)) == []


def test_formato_montado_nao_tem_achado_de_forma():
    """Afirmativas e asserção-razão: as alternativas são texto do sistema, e
    assimetria de tamanho entre elas não diz nada sobre a questão."""
    item = ItemObjetivo(
        enunciado="x",
        alternativas=[
            AlternativaAvaliavel("A", "I, apenas.", True, False),
            AlternativaAvaliavel(
                "B",
                "I e II, apenas, com um texto bem mais longo que o outro",
                False,
                True,
            ),
        ],
        trechos_base=[],
        identificadores_fonte=[],
        formato=FormatoItem.AFIRMATIVAS,
    )
    assert achados_de_forma(item) == []
