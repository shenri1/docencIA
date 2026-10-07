"""Leitura de prova — Núcleo Determinístico.

prova é o que o aluno vê. O que NÃO existe aqui é tão importante quanto
o que existe — nenhum dataclass tem campo para alternativa correta,
`letra_atribuida`, `ordem_alternativas`, aspectos esperados, justificativa ou
fonte interna. Vazar isso exigiria mudar o modelo de leitura, não esquecer um
`exclude`. Gabarito é.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.domain import EstadoProva, FaixaDificuldade, TipoQuestao
from backend.app.exceptions import ProvaNaoEncontradaException, ProvasNaoMontadasException
from backend.app.models.banco import BancoQuestoes, Questao
from backend.app.models.identidade import Docente
from backend.app.models.provas import ItemProva, Prova
from backend.app.services.provas.montagem_service import VERSAO_A, VERSAO_B, ProvasMontadas
from backend.app.services.provas.verificacao import verificar_provas


_CARREGAR_ITENS = (
    selectinload(Prova.itens).selectinload(ItemProva.questao).selectinload(Questao.alternativas)
)


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
    prova = db.get(
        Prova,
        prova_id,
        options=[_CARREGAR_ITENS],
    )
    if prova is None or prova.sessao.docente_id != docente.id:
        raise ProvaNaoEncontradaException(prova_id)
    return prova


def letras_na_prova(item: ItemProva) -> dict[str, str]:
    """Letra ORIGINAL → letra DA PROVA.

    `ordem_alternativas[i]` é a original que aparece na posição i, e a posição i
    recebe a i-ésima letra ordenada. Existe em um lugar só: a exibição da prova
 e o gabarito usam esta função, e duas implementações
    da mesma permutação divergiriam na primeira mudança.
    """
    if item.questao.tipo is not TipoQuestao.OBJETIVA:
        return {}
    destinos = sorted(a.letra for a in item.questao.alternativas)
    return dict(zip(item.ordem_alternativas or [], destinos, strict=True))


def _alternativas_lidas(item: ItemProva) -> list[AlternativaLida]:
    por_letra = {a.letra: a for a in item.questao.alternativas}
    return sorted(
        (
            AlternativaLida(letra=destino, texto=por_letra[original].texto)
            for original, destino in letras_na_prova(item).items()
        ),
        key=lambda alternativa: alternativa.letra,
    )


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


def provas_do_banco(db: Session, banco: BancoQuestoes) -> ProvasMontadas:
    """Frontend o que `montar_provas` devolveu, recalculado do estado
    gravado a cada pedido — como o marco. Sem isto, recarregar a página no M10
    deixaria o front sem os ids das provas."""
    por_versao = {
        prova.versao: prova
        for prova in db.scalars(
            select(Prova)
            .where(Prova.banco_id == banco.id)
            .options(_CARREGAR_ITENS)
        )
    }
    prova_a, prova_b = por_versao.get(VERSAO_A), por_versao.get(VERSAO_B)
    if prova_a is None or prova_b is None:
        raise ProvasNaoMontadasException(banco.versao)

    numeros_b = {item.questao.numero for item in prova_b.itens}
    # Mesma definição da seleção: questões distintas das duas provas.
    selecionadas = {
        item.questao.id: item.questao
        for prova in (prova_a, prova_b)
        for item in prova.itens
    }
    return ProvasMontadas(
        prova_a_id=prova_a.id,
        prova_b_id=prova_b.id,
        revisao_banco=prova_a.revisao_banco,
        compartilhadas=sorted(
            item.questao.numero
            for item in prova_a.itens
            if item.questao.numero in numeros_b
        ),
        sem_subtema=sum(1 for q in selecionadas.values() if q.subtema is None),
        verificacao=verificar_provas(db, prova_a, prova_b),
    )
