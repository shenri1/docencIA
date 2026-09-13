from sqlalchemy import event
from sqlalchemy.orm import configure_mappers

from backend.app.models import Base, RegistroAuditoria
from backend.app.models.base import bloquear_mutacao
from backend.app.models.identidade import Docente

TABELAS_ESPERADAS = {
    "docentes",
    "sessoes_geracao",
    "materiais_referencia",
    "chunks_material",
    "prompts_mestres",
    "provedores_llm",
    "consumos_token",
    "bancos_questoes",
    "questoes",
    "alternativas",
    "fontes_internas",
    "justificativas_estruturadas",
    "registros_exclusao",
    "relatorios_impacto",
    "provas",
    "itens_prova",
    "gabaritos",
    "exportacoes_docx",
    "registros_auditoria",
}


def test_todas_as_entidades_mapeadas():
    configure_mappers()
    assert set(Base.metadata.tables) == TABELAS_ESPERADAS


def test_tabelas_auditoria_sao_append_only():
    for evento in ("before_update", "before_delete"):
        assert event.contains(RegistroAuditoria, evento, bloquear_mutacao)
    try:
        bloquear_mutacao(None, None, RegistroAuditoria())
    except ValueError:
        return
    raise AssertionError("mutação em tabela append-only não foi bloqueada")


def test_docente_tem_coluna_senha_hash():
    colunas = {c.name for c in Docente.__table__.columns}
    assert "senha_hash" in colunas


if __name__ == "__main__":
    test_todas_as_entidades_mapeadas()
    test_tabelas_auditoria_sao_append_only()
    print("ok")
