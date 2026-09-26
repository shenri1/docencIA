from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from backend.app.core.config import settings
from backend.app.models import Base

RAIZ = Path(__file__).resolve().parents[2]
BANCO_MIGRACAO = "docencia_migracao_test"


@pytest.fixture(scope="module")
def engine_migrado():
    """Banco construído SÓ por migração — é isso que torna a comparação com
    os models significativa."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    # "postgres" é o banco de manutenção que existe em qualquer instância —
    # nunca depender do banco de dev "docencia" para emitir CREATE DATABASE.
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        # Enum types criados por op.create_table não são derrubados pelo
        # downgrade; recriar o banco do zero garante uma base limpa.
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    eng = create_engine(url)
    yield eng
    eng.dispose()


def test_migracao_reproduz_os_models_sem_diferenca(engine_migrado):
    with engine_migrado.connect() as conexao:
        contexto = MigrationContext.configure(
            conexao, opts={"compare_type": True, "include_schemas": False}
        )
        diferencas = compare_metadata(contexto, Base.metadata)
    assert diferencas == [], f"Migração fora de sincronia com os models: {diferencas}"


def test_seed_cria_a_cadeia_de_fallback(engine_migrado):
    with engine_migrado.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT nome, modelo, prioridade, endpoint, "
                "referencia_chave_secrets FROM provedores_llm "
                "WHERE ativo = true ORDER BY prioridade"
            )
        ).all()

    assert [(linha[0], linha[1], linha[2]) for linha in linhas] == [
        ("ollama-qwen3-4b", "qwen3:4b", 1),
        ("ollama-qwen3-1.7b", "qwen3:1.7b", 2),
    ]
    # endpoint NULL = usar settings.llm_base_url, que difere entre local e
    # Compose. Gravar um host aqui quebraria um dos dois ambientes.
    assert all(linha[3] is None for linha in linhas)
    assert all(linha[4] is None for linha in linhas)


BANCO_MIGRACAO_DADOS = "docencia_migracao_dados_test"


def test_migracao_10c_preserva_bancos_e_questoes_existentes():
    """Questões objetivas geradas antes da 10c continuam válidas: viram
    tipo OBJETIVA, e o banco ganha n_alvo_objetivas = n_alvo."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO_DADOS}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO_DADOS}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO_DADOS}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "e5b2c9d71a40")

    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana01', 'x', 'DOCENTE') "
                    "RETURNING id"
                )
            ).scalar_one()
            sessao_id = conn.execute(
                text(
                    "INSERT INTO sessoes_geracao (docente_id, disciplina, periodo, "
                    "k_alternativas, p_f, p_m, p_d, estado) VALUES "
                    "(:d, 'Algoritmos', '2026.2', 5, 30, 40, 30, "
                    "'MATERIAIS_CONFIRMADOS') RETURNING id"
                ),
                {"d": docente_id},
            ).scalar_one()
            banco_id = conn.execute(
                text(
                    "INSERT INTO bancos_questoes (sessao_id, versao, estado, n_alvo, "
                    "n_atual) VALUES (:s, 'v1', 'ABERTO', 7, 1) RETURNING id"
                ),
                {"s": sessao_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO questoes (banco_id, numero, enunciado, nivel_bloom, "
                    "faixa_dificuldade, estado) VALUES "
                    "(:b, 1, 'Qual?', 'APLICAR', 'MEDIA', 'ATIVA')"
                ),
                {"b": banco_id},
            )

        command.upgrade(cfg, "head")

        with eng.connect() as conn:
            assert conn.execute(text("SELECT tipo FROM questoes")).scalar_one() == (
                "OBJETIVA"
            )
            linha = conn.execute(
                text(
                    "SELECT n_alvo_objetivas, n_alvo_discursivas FROM bancos_questoes"
                )
            ).one()
            assert tuple(linha) == (7, 0)
    finally:
        eng.dispose()
