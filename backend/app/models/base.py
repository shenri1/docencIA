from sqlalchemy import MetaData, event
from sqlalchemy.orm import DeclarativeBase

# Nomes determinísticos de constraint (índice, FK, unique, check) — exigência
# do Alembic para autogenerate e migrations reversíveis.
CONVENCAO = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO)


def bloquear_mutacao(_mapper, _connection, target) -> None:
    raise ValueError(f"{type(target).__name__} é append-only")


def append_only(*modelos: type[Base]) -> None:
    """Torna tabelas imutáveis: UPDATE/DELETE levantam erro."""
    for modelo in modelos:
        event.listen(modelo, "before_update", bloquear_mutacao)
        event.listen(modelo, "before_delete", bloquear_mutacao)
