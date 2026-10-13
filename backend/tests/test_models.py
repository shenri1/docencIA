import pytest
from sqlalchemy import event
from sqlalchemy.orm import configure_mappers

from backend.app.domain import FormatoArquivo, OrigemTexto
from backend.app.models import Base, RegistroAuditoria
from backend.app.models.base import bloquear_mutacao
from backend.app.models.materiais import MaterialReferencia

TABELAS_ESPERADAS = {
    "docentes",
    "orientacoes_docente",
    "questoes_orientacoes",
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
    "registros_substituicao",
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


def test_indice_parcial_permite_substituida_repetida_e_veta_dois_ocupantes(
    db_session, sessao_rascunho
):
    """A regra do número é do banco de dados, não só do código: duas ATIVA no
    mesmo número são impossíveis, mas duas SUBSTITUIDA são o caso normal da
    segunda troca do mesmo número."""
    from sqlalchemy.exc import IntegrityError

    from backend.app.domain import EstadoQuestao
    from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva

    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    criar_questao_objetiva(db_session, banco, numero=1)
    criar_questao_objetiva(db_session, banco, numero=1, estado=EstadoQuestao.SUBSTITUIDA)
    criar_questao_objetiva(db_session, banco, numero=1, estado=EstadoQuestao.SUBSTITUIDA)
    criar_questao_objetiva(db_session, banco, numero=1, estado=EstadoQuestao.CANDIDATA)
    db_session.commit()

    # A fábrica faz flush: o índice dispara ali, não no commit.
    with pytest.raises(IntegrityError):
        criar_questao_objetiva(db_session, banco, numero=1)
    db_session.rollback()


def test_indice_parcial_veta_duas_candidatas_no_mesmo_numero(
    db_session, sessao_rascunho
):
    from sqlalchemy.exc import IntegrityError

    from backend.app.domain import EstadoQuestao
    from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva

    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=3)
    criar_questao_objetiva(db_session, banco, numero=2, estado=EstadoQuestao.CANDIDATA)
    db_session.commit()
    with pytest.raises(IntegrityError):
        criar_questao_objetiva(
            db_session, banco, numero=2, estado=EstadoQuestao.CANDIDATA
        )
    db_session.rollback()


def test_item_de_prova_discursiva_nao_tem_letra_nem_ordem(db_session, sessao_rascunho):
    """ é sobre alternativas, e discursiva não tem nenhuma."""
    from backend.app.domain import EstadoProva
    from backend.app.models.provas import ItemProva, Prova
    from backend.tests.fabrica_banco import criar_banco, criar_questao_discursiva

    banco = criar_banco(db_session, sessao_rascunho, n_discursivas=1)
    questao = criar_questao_discursiva(db_session, banco, numero=1)
    prova = Prova(
        sessao_id=sessao_rascunho.id,
        banco_id=banco.id,
        versao="A",
        n_questoes=1,
        n_objetivas=0,
        n_discursivas=1,
        revisao_banco=banco.revisao,
        estado=EstadoProva.MONTADA,
    )
    db_session.add(prova)
    db_session.flush()
    db_session.add(
        ItemProva(
            prova_id=prova.id,
            questao_id=questao.id,
            posicao=1,
            letra_atribuida=None,
            ordem_alternativas=None,
        )
    )
    db_session.commit()
    assert db_session.query(ItemProva).one().letra_atribuida is None


def test_prova_exige_soma_dos_tipos(db_session, sessao_rascunho):
    from sqlalchemy.exc import IntegrityError

    from backend.app.models.provas import Prova
    from backend.tests.fabrica_banco import criar_banco

    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=2)
    db_session.add(
        Prova(
            sessao_id=sessao_rascunho.id,
            banco_id=banco.id,
            versao="A",
            n_questoes=5,  # não é 2 + 1
            n_objetivas=2,
            n_discursivas=1,
            revisao_banco=banco.revisao,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def _exportacao(db, sessao, **extras):
    from backend.app.domain import TipoExportacao
    from backend.app.models.provas import ExportacaoDocx
    from backend.tests.fabrica_banco import criar_banco

    banco = criar_banco(db, sessao, n_objetivas=1)
    dados = {
        "banco_id": banco.id,
        "revisao_banco": 3,
        "tipo": TipoExportacao.CONTEUDO_PURO,
        "caminho_arquivo": "1/1/exportacoes/x.docx",
        "hash_conteudo": "a" * 64,
    }
    dados.update(extras)
    exportacao = ExportacaoDocx(**dados)
    db.add(exportacao)
    db.commit()
    return exportacao


def test_exportacao_grava_revisao_e_data(db_session, sessao_rascunho):
    exportacao = _exportacao(db_session, sessao_rascunho)
    db_session.refresh(exportacao)
    assert exportacao.revisao_banco == 3
    assert exportacao.criado_em is not None


def test_exportacao_e_unica_por_banco_revisao_e_tipo(db_session, sessao_rascunho):
    from sqlalchemy.exc import IntegrityError

    from backend.app.models.provas import ExportacaoDocx

    primeira = _exportacao(db_session, sessao_rascunho)
    db_session.add(
        ExportacaoDocx(
            banco_id=primeira.banco_id,
            revisao_banco=3,
            tipo=primeira.tipo,
            caminho_arquivo="outra",
            hash_conteudo="b" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_exportacao_e_append_only(db_session, sessao_rascunho):
    """O que saiu do sistema não é reescrito."""
    exportacao = _exportacao(db_session, sessao_rascunho)
    exportacao.hash_conteudo = "c" * 64
    with pytest.raises(ValueError, match="append-only"):
        db_session.flush()
    db_session.rollback()


def _orientacao(sessao_id: int, **campos):
    from backend.app.domain import EstadoOrientacao, OrigemOrientacao
    from backend.app.models.orientacoes import OrientacaoDocente

    base = {
        "sessao_id": sessao_id,
        "origem": OrigemOrientacao.SESSAO,
        "estado": EstadoOrientacao.ATIVA,
        "o_que_mudar": "prefiro exemplos práticos",
    }
    base.update(campos)
    return OrientacaoDocente(**base)


def test_orientacao_exige_algum_texto(db_session, sessao_rascunho):
    from sqlalchemy.exc import IntegrityError

    db_session.add(_orientacao(sessao_rascunho.id, o_que_mudar=None))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_orientacao_de_sessao_nao_tem_banco_nem_cruzamento(db_session, sessao_rascunho):
    from sqlalchemy.exc import IntegrityError

    db_session.add(_orientacao(sessao_rascunho.id, cruzar_com="redes"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_orientacao_de_questao_exige_banco_e_numero(db_session, sessao_rascunho):
    from sqlalchemy.exc import IntegrityError

    from backend.app.domain import OrigemOrientacao

    db_session.add(_orientacao(sessao_rascunho.id, origem=OrigemOrientacao.QUESTAO))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_pontual_so_existe_com_origem_questao(db_session, sessao_rascunho):
    from sqlalchemy.exc import IntegrityError

    from backend.app.domain import EstadoOrientacao

    db_session.add(_orientacao(sessao_rascunho.id, estado=EstadoOrientacao.PONTUAL))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_orientacao_de_questao_valida_e_ligada_a_questao(db_session, sessao_rascunho):
    from sqlalchemy import select

    from backend.app.domain import EstadoOrientacao, OrigemOrientacao
    from backend.app.models.orientacoes import questoes_orientacoes
    from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva

    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    questao = criar_questao_objetiva(db_session, banco, numero=1)
    orientacao = _orientacao(
        sessao_rascunho.id,
        origem=OrigemOrientacao.QUESTAO,
        estado=EstadoOrientacao.PONTUAL,
        o_que_mudar=None,
        cruzar_com="arquitetura de computadores",
        banco_id=banco.id,
        numero_origem=1,
    )
    db_session.add(orientacao)
    questao.orientacoes = [orientacao]
    db_session.commit()

    ligacoes = db_session.execute(select(questoes_orientacoes)).all()
    assert [(q, o) for q, o in ligacoes] == [(questao.id, orientacao.id)]
    assert orientacao.criada_em is not None
