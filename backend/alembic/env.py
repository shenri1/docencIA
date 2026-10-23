import socket
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from backend.app.core.config import settings
from backend.app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _fora_do_compose(url: str) -> str:
    """O .env aponta para o host "db", nome do serviço no Compose. Fora da rede
    dos containers (alembic rodado na mão no host) ele não resolve: vale o
    Postgres publicado em localhost, a mesma troca que o dev.py faz."""
    destino = make_url(url)
    if destino.host != "db":
        return url
    try:
        socket.getaddrinfo("db", None)
    except socket.gaierror:
        return destino.set(host="localhost").render_as_string(hide_password=False)
    return url


def _url() -> str:
    # Um chamador programático pode injetar a URL (teste de drift); sem isso,
    # vale a configuração da aplicação.
    return config.get_main_option("sqlalchemy.url") or _fora_do_compose(
        settings.database_url
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=None)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
