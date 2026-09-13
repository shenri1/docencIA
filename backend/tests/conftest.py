from __future__ import annotations

import os

from collections.abc import Generator


def _env_local_database_url() -> str:
    """
    .env aponta DATABASE_URL pro host "db" (nome do serviço no Compose),
    só resolvível de dentro da rede docker. Testes rodam fora do container,
    então o host vira "localhost" — mesmo esquema usado por dev.py.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(root, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DATABASE_URL="):
                    return line.partition("=")[2].strip().replace("@db:", "@localhost:")
    return "postgresql+psycopg://docencia:changeme@localhost:5432/docencia"


os.environ.setdefault("DATABASE_URL", _env_local_database_url())

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.main import app
from backend.app.models import Base
from backend.app.models.identidade import Docente


@pytest.fixture(scope="session")
def engine():
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
