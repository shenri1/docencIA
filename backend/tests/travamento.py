"""Verifica, sem threads, que um comando segura o lock da linha do banco.

O gancho roda no meio do comando (num passo interno substituído por um espião)
e tenta travar a mesma linha de OUTRA conexão com NOWAIT. Se o comando segura o
lock (FOR UPDATE até o commit), a segunda conexão falha na hora; se não segura,
consegue — e o teste vê a diferença.
"""

from psycopg.errors import LockNotAvailable
from sqlalchemy import text
from sqlalchemy.exc import OperationalError


def linha_esta_livre(engine, tabela: str, id_: int) -> bool:
    """True se outra conexão conseguiria travar a linha agora.

    Só o "lock não disponível" do NOWAIT conta como travada. Qualquer outro
    OperationalError (conexão recusada, timeout) sobe: lido como "travada",
    ele faria `achados == [False]` passar sem que o comando segurasse lock
    nenhum."""
    with engine.connect() as conn:
        linha = conn.execute(
            text(f"SELECT id FROM {tabela} WHERE id = :i"), {"i": id_}
        ).first()
        # Linha que esta conexão não vê (inexistente ou não commitada) "trava"
        # sem erro e devolveria True: o espião não mediria nada.
        assert linha is not None, f"{tabela}:{id_} não é visível para esta conexão"
        try:
            conn.execute(
                text(f"SELECT id FROM {tabela} WHERE id = :i FOR UPDATE NOWAIT"),
                {"i": id_},
            )
            return True
        except OperationalError as exc:
            if isinstance(exc.orig, LockNotAvailable):
                return False
            raise


def linha_do_banco_esta_livre(engine, banco_id: int) -> bool:
    return linha_esta_livre(engine, "bancos_questoes", banco_id)


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
