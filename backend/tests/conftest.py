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
# Os testes usam as chaves default; sem isto o config recusa subir (fail-closed).
os.environ.setdefault("AMBIENTE", "desenvolvimento")

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import DuplicateDatabase
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import settings
from backend.app.core.db import get_db
from backend.app.core.storage import ArmazenamentoLocal, get_armazenamento
from backend.app.main import app
from backend.app.models import Base
from backend.app.models.auditoria import RegistroAuditoria
from backend.app.models.banco import (
    Alternativa,
    AspectoEsperado,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
    RegistroExclusao,
    RegistroSubstituicao,
    RelatorioImpacto,
    RevisaoQuestao,
)
from backend.app.models.identidade import Docente, SessaoGeracao
from backend.app.models.materiais import ChunkMaterial, MaterialReferencia
from backend.app.models.prompt_provedor import PromptMestre
from backend.app.models.provas import ExportacaoDocx, ItemProva, Prova
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.auth_service import registrar_docente
from backend.app.services.rag.embeddings import EmbeddingsFake, get_embeddings
from backend.app.services.rag.rerank import RerankerFake, get_reranker


def _auth(client, credencial="rag001") -> dict[str, str]:
    client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": credencial,
            "senha": "senhaforte123",
        },
    )
    login = client.post(
        "/auth/login", data={"username": credencial, "password": "senhaforte123"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# Ordem importa: filhos antes dos pais, senão a FK bloqueia o DELETE.
#
# Tabela que nasce num teste e não é limpa vaza para os seguintes. Foi o que
# aconteceu com `prompts_mestres`: a versão "1.0.0" do primeiro teste sobrevivia
# e os oito seguintes morriam com VersaoPromptDuplicadaException — cada um
# passava isolado e todos falhavam juntos.
_MODELOS_PARA_LIMPAR = (
    # Referencia FonteInterna e Questao — precisa sair antes de ambos.
    AspectoEsperado,
    # Filhos de Questao
    RevisaoQuestao,
    JustificativaEstruturada,
    Alternativa,
    FonteInterna,
    RegistroExclusao,
    RegistroSubstituicao,
    # Filho de Prova e de BancoQuestoes
    ExportacaoDocx,
    # Filhos de Questao e de BancoQuestoes
    ItemProva,
    Prova,
    # Filhos de BancoQuestoes
    Questao,
    RelatorioImpacto,
    BancoQuestoes,
    # Filhos de MaterialReferencia
    ChunkMaterial,
    MaterialReferencia,
    # Sem FK: pode sair em qualquer posição. Fica aqui para a lista continuar
    # lida de filho para pai.
    RegistroAuditoria,
    # Raízes
    SessaoGeracao,
    Docente,
    # Sem FK, mas com `versao` unique — é o caso que motivou esta lista.
    PromptMestre,
)


def _garantir_banco_de_teste_existe() -> None:
    """
    Postgres não cria bancos sob demanda — antes de apontar o engine de
    teste pra "docencia_test", conecta no banco de manutenção "postgres"
    (que existe em qualquer instância) em modo autocommit e cria
    "docencia_test" se ainda não existir.
    """
    url_admin = settings.database_url.rsplit("/", 1)[0] + "/postgres"
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
    # Mesma configuração do SessionLocal de produção (core/db.py): autoflush
    # desligado e objetos não expiram no commit. Sem isso, testes que simulam
    # leitura obsoleta (race de upload × confirmar) acabariam re-flushando o
    # estado velho pro banco e mascarando o comportamento real.
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.rollback()
    for modelo in _MODELOS_PARA_LIMPAR:
        session.query(modelo).delete()
    session.commit()
    session.close()


@pytest.fixture()
def docente(db_session) -> Docente:
    return registrar_docente(
        db_session,
        DocenteCriar(
            nome="Ana Souza",
            credencial_institucional="prof-materiais",
            senha="senhaforte123",
        ),
    )


@pytest.fixture()
def armazenamento(tmp_path) -> ArmazenamentoLocal:
    return ArmazenamentoLocal(tmp_path / "storage")


@pytest.fixture()
def embeddings_fake() -> EmbeddingsFake:
    return EmbeddingsFake()


@pytest.fixture()
def reranker_fake() -> RerankerFake:
    return RerankerFake()


@pytest.fixture()
def sessao_rascunho(db_session, docente) -> SessaoGeracao:
    from backend.app.schemas.sessao import SessaoCriar
    from backend.app.services.sessao_service import criar_sessao

    return criar_sessao(
        db_session,
        docente,
        SessaoCriar(
            disciplina="Algoritmos",
            periodo="2026.2",
            tema_escopo="Grafos",
            area_do_conhecimento="Computação",
            k_alternativas=5,
            p_f=30,
            p_m=40,
            p_d=30,
        ),
    )


@pytest.fixture()
def client(
    db_session, armazenamento, embeddings_fake, reranker_fake
) -> Generator[TestClient]:
    def _override_get_db() -> Generator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_armazenamento] = lambda: armazenamento
    app.dependency_overrides[get_embeddings] = lambda: embeddings_fake
    app.dependency_overrides[get_reranker] = lambda: reranker_fake
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
