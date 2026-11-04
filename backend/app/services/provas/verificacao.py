"""Verificação pós-montagem — Núcleo Determinístico, puro sobre o persistido.

O critério de aceitação é "verificação automática pós-montagem
identifica zero violações das regras de distribuição de letras", e o da sobreposição temática é
"auditoria final detecta zero violações da regra de sobreposição". Esta função é
essas duas auditorias.

Ela DEVOLVE a lista em vez de levantar: no GET ela é relatório. Quem levanta é a
montagem, que se recusa a entregar o que a verificação recusa.

Não é gravada: é recalculável a partir das ItemProva a qualquer momento, e coluna
derivada seria mais um lugar para divergir.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.domain import TipoQuestao
from backend.app.models.provas import ItemProva, Prova
from backend.app.schemas.geracao import LETRAS
from backend.app.services.provas.letras import (
    JANELA_MONOTONA,
    LIMITE_COLISAO_DIVISOR,
    periodo_minimo,
    tem_deriva_monotona,
    tem_progressao_aritmetica,
)
from backend.app.services.provas.selecao import LIMITE_SUBTEMA_COMPARTILHADO


@dataclass(frozen=True)
class Verificacao:
    # Vazia é o resultado esperado.
    violacoes: list[str]
    colisoes_letras: int
    posicoes_objetivas: int
    compartilhadas: int
    subtemas_compartilhados: dict[str, int]


def _itens(prova: Prova) -> list[ItemProva]:
    return sorted(prova.itens, key=lambda item: item.posicao)


def _objetivos(prova: Prova) -> list[ItemProva]:
    return [item for item in _itens(prova) if item.questao.tipo is TipoQuestao.OBJETIVA]


def _violacoes_das_letras(prova: Prova) -> list[str]:
    itens = _objetivos(prova)
    if not itens:
        return []
    indices = [LETRAS.index(item.letra_atribuida) for item in itens]
    k = prova.sessao.k_alternativas
    problemas: list[str] = []

    contagens = [indices.count(letra) for letra in range(k)]
    if max(contagens) - min(contagens) > 1:
        problemas.append(
            f"{prova.versao}: contagem de letras difere em "
            f"{max(contagens) - min(contagens)}, esperado no máximo 1"
        )
    if tem_progressao_aritmetica(indices):
        problemas.append(
            f"{prova.versao}: há trinca consecutiva em progressão aritmética "
            "nas letras"
        )
    periodo = periodo_minimo(indices)
    if periodo * 2 <= len(indices):
        problemas.append(
            f"{prova.versao}: letras têm período {periodo} em {len(indices)} "
            "posições, padrão repetitivo"
        )
    if tem_deriva_monotona(indices):
        problemas.append(
            f"{prova.versao}: há janela de {JANELA_MONOTONA} posições com deriva "
            "monótona nas letras"
        )
    return problemas


def _violacoes_da_permutacao(prova: Prova) -> list[str]:
    problemas: list[str] = []
    for item in _itens(prova):
        rotulo = f"{prova.versao} pos.{item.posicao}"
        if item.questao.tipo is not TipoQuestao.OBJETIVA:
            if item.letra_atribuida is not None or item.ordem_alternativas is not None:
                problemas.append(
                    f"{rotulo}: discursiva com letra ou ordem de alternativas"
                )
            continue
        originais = sorted(a.letra for a in item.questao.alternativas)
        ordem = item.ordem_alternativas or []
        if sorted(ordem) != originais:
            problemas.append(
                f"{rotulo}: ordem_alternativas não é permutação de {''.join(originais)}"
            )
            continue
        correta = next(a.letra for a in item.questao.alternativas if a.correta)
        destino = originais[ordem.index(correta)]
        if destino != item.letra_atribuida:
            problemas.append(
                f"{rotulo}: a correta cai em {destino}, esperado {item.letra_atribuida}"
            )
    return problemas


def _violacoes_da_composicao(prova: Prova) -> list[str]:
    itens = _itens(prova)
    problemas: list[str] = []
    if len(itens) != prova.n_questoes:
        problemas.append(
            f"{prova.versao}: {len(itens)} itens, esperado {prova.n_questoes}"
        )
    if [item.posicao for item in itens] != list(range(1, len(itens) + 1)):
        problemas.append(f"{prova.versao}: posições com buraco ou fora de ordem")
    objetivas = sum(1 for item in itens if item.questao.tipo is TipoQuestao.OBJETIVA)
    if objetivas != prova.n_objetivas:
        problemas.append(
            f"{prova.versao}: {objetivas} objetivas, esperado {prova.n_objetivas}"
        )
    # A proporção por faixa não é conferida aqui: ela vale na geração do banco,
    # e a composição de cada prova é escolha do docente.
    return problemas


def verificar_provas(db: Session, prova_a: Prova, prova_b: Prova) -> Verificacao:
    problemas: list[str] = []
    for prova in (prova_a, prova_b):
        problemas.extend(_violacoes_das_letras(prova))
        problemas.extend(_violacoes_da_permutacao(prova))
        problemas.extend(_violacoes_da_composicao(prova))

    objetivos_a, objetivos_b = _objetivos(prova_a), _objetivos(prova_b)
    colisoes = sum(
        1
        for item_a, item_b in zip(objetivos_a, objetivos_b, strict=False)
        if item_a.letra_atribuida == item_b.letra_atribuida
    )
    posicoes = min(len(objetivos_a), len(objetivos_b))
    if colisoes * LIMITE_COLISAO_DIVISOR > posicoes:
        problemas.append(
            f"{colisoes} colisões de letra: de {posicoes} posições objetivas, "
            "mais da metade tem a mesma letra em A e em B"
        )

    questoes_a = {item.questao_id: item.questao for item in _itens(prova_a)}
    questoes_b = {item.questao_id: item.questao for item in _itens(prova_b)}
    compartilhadas = [
        questoes_a[questao_id] for questao_id in questoes_a.keys() & questoes_b.keys()
    ]
    # Subtema NULL nunca colide: duas questões sem subtema não são "o mesmo
    # subtema", e a regra fica declaradamente cega para elas.
    contagem = Counter(
        questao.subtema for questao in compartilhadas if questao.subtema is not None
    )
    for subtema, quantas in sorted(contagem.items()):
        if quantas > LIMITE_SUBTEMA_COMPARTILHADO:
            problemas.append(
                f'subtema "{subtema}" aparece em {quantas} questões nas duas '
                f"provas, acima do limite de {LIMITE_SUBTEMA_COMPARTILHADO}"
            )

    if prova_a.revisao_banco != prova_b.revisao_banco:
        problemas.append(
            f"A foi montada na revisão {prova_a.revisao_banco} e B na "
            f"{prova_b.revisao_banco}"
        )
    elif prova_a.revisao_banco != prova_a.banco.revisao:
        problemas.append(
            f"provas montadas na revisão {prova_a.revisao_banco}, banco está na "
            f"{prova_a.banco.revisao}"
        )

    return Verificacao(
        violacoes=problemas,
        colisoes_letras=colisoes,
        posicoes_objetivas=posicoes,
        compartilhadas=len(compartilhadas),
        subtemas_compartilhados=dict(contagem),
    )
