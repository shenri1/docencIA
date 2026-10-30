"""Lê questões ATIVAS do Postgres por SQL puro e devolve objetos para `amostras`.

SQL e não o ORM porque este pacote roda num Python 3.12 (o `ragas` não instala
no 3.14 do app) e o app usa sintaxe que só o 3.14 aceita. É leitura: nenhum
INSERT/UPDATE, e nada de `materiais`, `chunks` ou dados do docente além do que
a questão cita.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from types import SimpleNamespace


def montar_questoes(
    questoes: Iterable[Mapping],
    alternativas: Iterable[Mapping],
    fontes: Iterable[Mapping],
    justificativas: Iterable[Mapping],
    aspectos: Iterable[Mapping],
) -> list[SimpleNamespace]:
    def por_questao(linhas: Iterable[Mapping]) -> dict[int, list[SimpleNamespace]]:
        grupos = defaultdict(list)
        for linha in linhas:
            grupos[linha["questao_id"]].append(SimpleNamespace(**linha))
        return grupos

    alts, fts, asp = por_questao(alternativas), por_questao(fontes), por_questao(aspectos)
    just = {j["questao_id"]: SimpleNamespace(**j) for j in justificativas}
    return [
        SimpleNamespace(
            **q,
            alternativas=alts[q["id"]],
            fontes_internas=fts[q["id"]],
            aspectos=asp[q["id"]],
            justificativa=just.get(q["id"]),
        )
        for q in questoes
    ]


_QUESTOES = """
SELECT q.id, q.numero, q.tipo::text AS tipo, q.formato::text AS formato,
       q.enunciado, q.tema
FROM questoes q JOIN bancos_questoes b ON b.id = q.banco_id
WHERE b.sessao_id = %(sessao)s AND q.estado = 'ATIVA'
ORDER BY b.id, q.numero
"""
_FILHOS = {
    "alternativas": "SELECT questao_id, letra, texto, correta FROM alternativas",
    "fontes": "SELECT questao_id, localizacao, trecho_base FROM fontes_internas",
    "justificativas": (
        "SELECT questao_id, justificativa_correta, estrutura_formato "
        "FROM justificativas_estruturadas"
    ),
    "aspectos": "SELECT questao_id, ordem, texto FROM aspectos_esperados",
}


def carregar_da_sessao(url: str, sessao_id: int) -> list[SimpleNamespace]:
    import psycopg  # import tardio: os testes de `montar_questoes` não precisam dele
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row) as conexao:
        questoes = conexao.execute(_QUESTOES, {"sessao": sessao_id}).fetchall()
        ids = [q["id"] for q in questoes]
        filhos = {
            nome: conexao.execute(
                f"{sql} WHERE questao_id = ANY(%(ids)s)", {"ids": ids}
            ).fetchall()
            for nome, sql in _FILHOS.items()
        }
    return montar_questoes(questoes, **filhos)
