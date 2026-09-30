"""Verifica, sem threads, que um comando segura o lock da linha do banco.

O gancho roda no meio do comando (num passo interno substituído por um espião)
e tenta travar a mesma linha de OUTRA conexão com NOWAIT. Se o comando segura o
lock (FOR UPDATE até o commit), a segunda conexão falha na hora; se não segura,
consegue — e o teste vê a diferença.
"""

from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def linha_do_banco_esta_livre(engine, banco_id: int) -> bool:
    """True se outra conexão conseguiria travar a linha agora."""
    with engine.connect() as conn:
        try:
            conn.execute(
                text("SELECT id FROM bancos_questoes WHERE id = :i FOR UPDATE NOWAIT"),
                {"i": banco_id},
            )
            return True
        except OperationalError:
            return False


def espiar_lock(monkeypatch, modulo, nome: str, engine, banco_id: int) -> list[bool]:
    """Troca `modulo.nome` por um espião que registra se a linha estava livre
    no momento da chamada. Devolve a lista onde os achados são acumulados."""
    achados: list[bool] = []
    original = getattr(modulo, nome)

    def com_espia(*args, **kwargs):
        achados.append(linha_do_banco_esta_livre(engine, banco_id))
        return original(*args, **kwargs)

    monkeypatch.setattr(modulo, nome, com_espia)
    return achados
