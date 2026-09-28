"""Leitura de prova — Núcleo Determinístico.

prova é o que o aluno vê. O que NÃO existe aqui é tão importante quanto
o que existe — nenhum dataclass tem campo para alternativa correta,
`letra_atribuida`, `ordem_alternativas`, aspectos esperados, justificativa ou
fonte interna. Vazar isso exigiria mudar o modelo de leitura, não esquecer um
`exclude`. Gabarito é.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.domain import EstadoProva, FaixaDificuldade, TipoQuestao
from backend.app.exceptions import ProvaNaoEncontradaException
from backend.app.models.identidade import Docente
from backend.app.models.provas import ItemProva, Prova
from backend.app.services.provas.montagem_service import VERSAO_A, VERSAO_B


@dataclass(frozen=True)
class AlternativaLida:
    # Letra DA PROVA, não a original.
    letra: str
    texto: str


@dataclass(frozen=True)
class ItemLido:
    posicao: int
    numero: int
    tipo: TipoQuestao
    faixa_dificuldade: FaixaDificuldade
    enunciado: str
    # Vazia na discursiva.
    alternativas: list[AlternativaLida]


@dataclass(frozen=True)
class ProvaLida:
    prova_id: int
    versao: str
    estado: EstadoProva
    n_questoes: int
    n_objetivas: int
    n_discursivas: int
    revisao_banco: int
    banco_revisao_atual: int
    # A comparação de inteiros que prometeu. Quem bloqueia de fato é
    # na exportação; aqui é aviso.
    desatualizada: bool
    itens: list[ItemLido]


def obter_prova(db: Session, docente: Docente, prova_id: int) -> Prova:
    """Prova de outro docente responde 404, não 403 — mesma regra de banco e
    sessão: não revela existência."""
    prova = db.get(Prova, prova_id)
    if prova is None or prova.sessao.docente_id != docente.id:
        raise ProvaNaoEncontradaException(prova_id)
    return prova


def _alternativas_lidas(item: ItemProva) -> list[AlternativaLida]:
    if item.questao.tipo is not TipoQuestao.OBJETIVA:
        return []
    por_letra = {a.letra: a for a in item.questao.alternativas}
    destinos = sorted(por_letra)
    # ordem_alternativas[i] é a letra ORIGINAL que aparece na posição i, e
    # destinos[i] é a letra que ela recebe na prova.
    return [
        AlternativaLida(letra=destino, texto=por_letra[original].texto)
        for destino, original in zip(
            destinos, item.ordem_alternativas or [], strict=True
        )
    ]


def ler_prova(db: Session, docente: Docente, prova_id: int) -> ProvaLida:
    prova = obter_prova(db, docente, prova_id)
    revisao_atual = prova.banco.revisao
    return ProvaLida(
        prova_id=prova.id,
        versao=prova.versao,
        estado=prova.estado,
        n_questoes=prova.n_questoes,
        n_objetivas=prova.n_objetivas,
        n_discursivas=prova.n_discursivas,
        revisao_banco=prova.revisao_banco,
        banco_revisao_atual=revisao_atual,
        desatualizada=prova.revisao_banco != revisao_atual,
        itens=[
            ItemLido(
                posicao=item.posicao,
                numero=item.questao.numero,
                tipo=item.questao.tipo,
                faixa_dificuldade=item.questao.faixa_dificuldade,
                enunciado=item.questao.enunciado,
                alternativas=_alternativas_lidas(item),
            )
            for item in sorted(prova.itens, key=lambda i: i.posicao)
        ],
    )


def par_da_prova(db: Session, prova: Prova) -> Prova:
    """A outra versão da mesma sessão. A verificação é sobre o PAR: uma prova
    sozinha não tem colisão de letras nem sobreposição."""
    outra = VERSAO_B if prova.versao == VERSAO_A else VERSAO_A
    par = next((p for p in prova.sessao.provas if p.versao == outra), None)
    if par is None:
        raise ProvaNaoEncontradaException(prova.id)
    return par
