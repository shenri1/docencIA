from contextlib import contextmanager

from sqlalchemy import event


@contextmanager
def contar_queries(db):
    """Conta os SELECTs emitidos no bloco. `expire_all` antes: sem isso os
    objetos da fábrica já estão no identity map e nenhum lazy load aparece."""
    db.expire_all()
    consultas: list[str] = []

    def _registrar(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT"):
            consultas.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _registrar)
    try:
        yield consultas
    finally:
        event.remove(engine, "before_cursor_execute", _registrar)
