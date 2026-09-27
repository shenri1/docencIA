from backend.app.domain import RiscoAuditoria
from backend.app.services.critico.auditor_service import (
    achados_de_forma,
    item_de_questao,
)
from backend.tests.fabrica_banco_sintetico import (
    DEFEITOS_ESPERADOS,
    montar_banco_sintetico,
)

FORMA = [d for d in DEFEITOS_ESPERADOS if d.risco is RiscoAuditoria.ASSIMETRIA_FORMA]


def test_banco_sintetico_tem_cinco_questoes(db_session, sessao_rascunho):
    banco = montar_banco_sintetico(db_session, sessao_rascunho)
    assert len(banco.questoes) == 5
    assert banco.n_atual == 5


def test_auditoria_acha_todos_os_defeitos_de_forma(db_session, sessao_rascunho):
    """Parte determinística do critério de ≥90%: 100% dos defeitos de forma são
    achados, sem LLM nenhum."""
    banco = montar_banco_sintetico(db_session, sessao_rascunho)
    por_numero = {q.numero: q for q in banco.questoes}

    achados_por_numero = {
        numero: achados_de_forma(item_de_questao(questao, []))
        for numero, questao in por_numero.items()
    }

    for defeito in FORMA:
        achados = achados_por_numero[defeito.numero]
        assert achados, f"nenhum achado na Q{defeito.numero}: {defeito.por_que}"
        assert defeito.alvo in {a.alvo for a in achados}


def test_questao_sem_defeito_nao_gera_achado_de_forma(db_session, sessao_rascunho):
    """Falso positivo conta na avaliação: a Q5 é limpa de propósito."""
    banco = montar_banco_sintetico(db_session, sessao_rascunho)
    limpa = next(q for q in banco.questoes if q.numero == 5)
    assert achados_de_forma(item_de_questao(limpa, [])) == []
