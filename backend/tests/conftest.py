from __future__ import annotations

import os
from collections.abc import Generator


def _env_local_database_url() -> str:
    """
    .env aponta DATABASE_URL pro host "db" (nome do serviço no Compose),
    só resolvível de dentro da rede docker. Testes rodam fora do container,
    então o host vira "localhost" — mesmo esquema usado por dev.py.

    Além disso, os testes nunca devem rodar contra o banco "docencia" que
    dev.py e o compose usam — create_all/drop_all aqui apagaria dados reais
    do docente. Por isso o nome do banco na URL é sempre trocado para
    "docencia_test", isolado do banco de desenvolvimento.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(root, ".env")
    url = "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    url = line.partition("=")[2].strip().replace("@db:", "@localhost:")
                    break
    if url.endswith("/docencia"):
        url = url[: -len("/docencia")] + "/docencia_test"
    return url


os.environ.setdefault("DATABASE_URL", _env_local_database_url())

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import DuplicateDatabase
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models import Base
from backend.app.models.identidade import Docente


def _garantir_banco_de_teste_existe() -> None:
    """
    Postgres não cria bancos sob demanda — antes de apontar o engine de
    teste pra "docencia_test", conecta no banco de dev ("docencia") em modo
    autocommit e cria "docencia_test" se ainda não existir.
    """
    url_admin = settings.database_url.rsplit("/", 1)[0] + "/docencia"
    nome_banco_teste = settings.database_url.rsplit("/", 1)[1]
    admin_engine = create_engine(url_admin, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            try:
                conn.execute(text(f'CREATE DATABASE "{nome_banco_teste}"'))
            except ProgrammingError as exc:
                if not isinstance(exc.orig, DuplicateDatabase):
                    raise
    finally:
        admin_engine.dispose()

    # docencia_test é um banco novo — o script de init do compose que roda
    # `CREATE EXTENSION vector` só é executado pelo Postgres contra o banco
    # default ("docencia") na primeira subida do container.
    test_engine = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        with test_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    finally:
        test_engine.dispose()


@pytest.fixture(scope="session")
def engine():
    _garantir_banco_de_teste_existe()
    eng = create_engine(settings.database_url)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture()
def db_session(engine) -> Generator[Session]:
    session = sessionmaker(bind=engine)()
    yield session
    session.rollback()
    session.query(Docente).delete()
    session.commit()
    session.close()


@pytest.fixture()
def client(db_session) -> Generator[TestClient]:
    def _override_get_db() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
