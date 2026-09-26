import pytest
from sqlalchemy import event
from sqlalchemy.orm import configure_mappers

from backend.app.domain import FormatoArquivo, OrigemTexto
from backend.app.models import Base, RegistroAuditoria
from backend.app.models.base import bloquear_mutacao
from backend.app.models.materiais import MaterialReferencia

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
    "revisoes_questao",
    "registros_exclusao",
    "relatorios_impacto",
    "provas",
    "itens_prova",
    "gabaritos",
    "exportacoes_docx",
    "registros_auditoria",
    "aspectos_esperados",
}


def test_todas_as_entidades_mapeadas():
    configure_mappers()
    assert set(Base.metadata.tables) == TABELAS_ESPERADAS


def test_tabelas_auditoria_sao_append_only():
    for evento in ("before_update", "before_delete"):
        assert event.contains(RegistroAuditoria, evento, bloquear_mutacao)
    with pytest.raises(ValueError):
        bloquear_mutacao(None, None, RegistroAuditoria())


def test_material_tem_colunas_do_modulo_de_materiais():
    colunas = {c.name for c in MaterialReferencia.__table__.columns}
    assert {
        "formato",
        "chave_armazenamento",
        "chave_texto_extraido",
        "hash_sha256",
        "tamanho_bytes",
        "origem_texto",
        "criado_em",
    } <= colunas


def test_material_tem_unicidade_por_sessao():
    nomes = {
        constraint.name
        for constraint in MaterialReferencia.__table__.constraints
        if constraint.name
    }
    assert "material_por_sessao_hash" in nomes
    assert "material_por_sessao_identificador" in nomes


def test_enums_de_formato_e_origem():
    assert [f.value for f in FormatoArquivo] == ["pdf", "pptx", "docx", "txt"]
    assert [o.value for o in OrigemTexto] == ["nativo", "ocr", "misto"]


def test_chunk_tem_ordem_unica_por_material():
    from backend.app.models.materiais import ChunkMaterial

    assert "ordem" in ChunkMaterial.__table__.columns
    nomes = {c.name for c in ChunkMaterial.__table__.constraints}
    assert "chunk_por_material_ordem" in nomes


def test_vetor_embedding_usa_a_dimensao_configurada():
    from backend.app.core.config import settings
    from backend.app.models.materiais import ChunkMaterial

    tipo = ChunkMaterial.__table__.columns["vetor_embedding"].type
    assert tipo.dim == settings.embedding_dim == 1024


def test_provedor_llm_tem_modelo_e_prioridade():
    from backend.app.models.prompt_provedor import ProvedorLLM

    colunas = ProvedorLLM.__table__.columns
    # endpoint diz ONDE; faltava dizer O QUÊ.
    assert colunas["modelo"].nullable is False
    assert colunas["prioridade"].nullable is False
    # Provedor local não tem chave: string vazia seria mentira no schema.
    assert colunas["referencia_chave_secrets"].nullable is True
    # NULL = usar settings.llm_base_url, para a seed não fixar um host.
    assert colunas["endpoint"].nullable is True


def test_prompt_mestre_tem_criado_em_e_hash():
    from backend.app.models.prompt_provedor import PromptMestre

    colunas = PromptMestre.__table__.columns
    # Sem criado_em, o histórico só teria `id` para ordenar.
    assert colunas["criado_em"].nullable is False
    assert colunas["criado_em"].server_default is not None
    # 64 = SHA-256 em hexadecimal.
    assert colunas["hash_modulos"].type.length == 64


def test_revisao_questao_e_1_para_1_com_questao():
    from backend.app.models.banco import RevisaoQuestao

    colunas = RevisaoQuestao.__table__.columns
    assert colunas["questao_id"].unique is True
    for nome in ("rascunho", "violacoes_rascunho", "violacoes_final"):
        assert colunas[nome].type.__class__.__name__ == "JSONB"
        assert colunas[nome].nullable is False
    # O fallback pode servir as duas chamadas com modelos diferentes.
    assert colunas["modelo_geracao"].nullable is False
    assert colunas["modelo_revisao"].nullable is False


def test_questao_tem_tipo_obrigatorio():
    from backend.app.models.banco import Questao

    coluna = Questao.__table__.columns["tipo"]
    assert coluna.nullable is False
    # Sem default de servidor nem default Python: o código sempre diz o tipo
    # explicitamente (`_persistir` passa `tipo=item.tipo`).
    assert coluna.server_default is None


def test_aspecto_esperado_aponta_fonte_da_questao():
    from backend.app.models.banco import AspectoEsperado

    colunas = AspectoEsperado.__table__.columns
    assert colunas["fonte_interna_id"].nullable is False
    assert colunas["texto"].nullable is False
    nomes = {c.name for c in AspectoEsperado.__table__.constraints}
    assert "aspecto_por_questao_ordem" in nomes


def test_justificativa_so_exige_objetivo_cognitivo():
    from backend.app.models.banco import JustificativaEstruturada

    colunas = JustificativaEstruturada.__table__.columns
    assert colunas["objetivo_cognitivo"].nullable is False
    for nome in (
        "justificativa_correta",
        "invalidacao_distratores",
        "verificacao_unicidade",
        "texto_verificacao_unicidade",
    ):
        assert colunas[nome].nullable is True


def test_banco_guarda_contagem_por_tipo():
    from backend.app.models.banco import BancoQuestoes

    colunas = BancoQuestoes.__table__.columns
    assert colunas["n_alvo_objetivas"].nullable is False
    assert colunas["n_alvo_discursivas"].nullable is False
    nomes = {c.name for c in BancoQuestoes.__table__.constraints}
    assert "n_alvo_soma_tipos" in nomes
