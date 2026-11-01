import pytest

from avaliacao.ragas_avaliar import _url_do_banco


def test_url_do_env_vira_url_do_psycopg_no_host(monkeypatch):
    """A mesma DATABASE_URL do .env: sem o "+psycopg" do SQLAlchemy e com o host
    do Compose ("db") trocado por localhost, como faz o dev.py."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://docencia:x@db:5432/docencia"
    )
    assert _url_do_banco() == "postgresql://docencia:x@localhost:5432/docencia"


def test_sem_database_url_para_com_mensagem(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit, match="DATABASE_URL"):
        _url_do_banco()
