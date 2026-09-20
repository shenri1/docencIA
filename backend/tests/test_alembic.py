import subprocess
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


def test_alembic_esta_configurado():
    resultado = subprocess.run(
        ["uv", "run", "alembic", "heads"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def test_lifespan_nao_cria_schema():
    """Schema é responsabilidade exclusiva do Alembic a partir desta etapa."""
    fonte = (RAIZ / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "create_all" not in fonte


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
