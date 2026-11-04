"""Montagem das Provas A e B — orquestração de caso de uso.

As duas provas numa transação, por uma rota só: a regra de <= 50% de colisão de
letras e a de sobreposição de subtema são RELAÇÕES entre as duas versões. Um
estado intermediário com uma prova só seria inconsistente com ambas.

Nenhum LLM: montar prova é seleção e permutação sobre dados já persistidos.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import (
    EstadoBanco,
    EstadoProva,
    EstadoQuestao,
    EstadoSessao,
    TipoEventoAuditoria,
    TipoQuestao,
)
from backend.app.exceptions import (
    BancoNaoCongeladoException,
    MontagemInconsistenteException,
    ProvasJaMontadasException,
)
from backend.app.models.banco import BancoQuestoes, Questao
from backend.app.models.identidade import Docente
from backend.app.models.provas import ItemProva, Prova
from backend.app.services.controle_banco.consistencia import verificar_consistencia
from backend.app.services.controle_banco.estado import exigir_revisao, travar_banco
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.provas.letras import planejar_letras
from backend.app.services.provas.selecao import Selecao, escolher, selecionar
from backend.app.services.provas.verificacao import Verificacao, verificar_provas

VERSAO_A = "A"
VERSAO_B = "B"


@dataclass(frozen=True)
class ProvasMontadas:
    prova_a_id: int
    prova_b_id: int
    revisao_banco: int
    compartilhadas: list[int]
    sem_subtema: int
    verificacao: Verificacao


def _semente(sessao_id: int, versao: str, revisao: int, sufixo: str = "") -> str:
    """Derivada, nunca gravada: o resultado persistido é `letra_atribuida` e
    `ordem_alternativas`, e é sobre eles que a verificação roda."""
    return f"{sessao_id}:{versao}:{revisao}:{sufixo}"


def _ordem_das_alternativas(
    questao: Questao, letra_destino: str, gerador: random.Random
) -> list[str]:
    """Letras ORIGINAIS na ordem da prova, com a correta caindo em
    `letra_destino`. Embaralhar por item e por versão é o que impede comparar A
    com B pelos distratores."""
    originais = sorted(alternativa.letra for alternativa in questao.alternativas)
    correta = next(a.letra for a in questao.alternativas if a.correta)
    ordem = originais[:]
    gerador.shuffle(ordem)
    destino = originais.index(letra_destino)
    atual = ordem.index(correta)
    ordem[atual], ordem[destino] = ordem[destino], ordem[atual]
    return ordem


def _criar_prova(
    db: Session,
    banco: BancoQuestoes,
    versao: str,
    questoes: list[Questao],
    letras: list[str],
) -> Prova:
    objetivas = [q for q in questoes if q.tipo is TipoQuestao.OBJETIVA]
    prova = Prova(
        # Vem do banco, nunca da entrada: é o que a UniqueConstraint usa.
        sessao_id=banco.sessao_id,
        banco_id=banco.id,
        versao=versao,
        n_questoes=len(questoes),
        n_objetivas=len(objetivas),
        n_discursivas=len(questoes) - len(objetivas),
        revisao_banco=banco.revisao,
        estado=EstadoProva.MONTADA,
    )
    db.add(prova)
    db.flush()  # precisa do id para os itens

    gerador = random.Random(_semente(banco.sessao_id, versao, banco.revisao, "ordem"))
    proxima_letra = iter(letras)
    for posicao, questao in enumerate(questoes, start=1):
        if questao.tipo is TipoQuestao.OBJETIVA:
            letra = next(proxima_letra)
            ordem = _ordem_das_alternativas(questao, letra, gerador)
        else:
            # É sobre alternativas, e discursiva não tem nenhuma.
            letra, ordem = None, None
        db.add(
            ItemProva(
                prova_id=prova.id,
                questao_id=questao.id,
                posicao=posicao,
                letra_atribuida=letra,
                ordem_alternativas=ordem,
            )
        )
    db.flush()
    return prova


def _ativas(db: Session, banco: BancoQuestoes) -> list[Questao]:
    return list(
        db.scalars(
            select(Questao)
            .where(Questao.banco_id == banco.id, Questao.estado == EstadoQuestao.ATIVA)
            .order_by(Questao.numero)
        )
    )


def sugerir_selecao(
    db: Session, banco: BancoQuestoes, n_objetivas: int, n_discursivas: int
) -> Selecao:
    """A seleção automática, sem gravar nada: o docente parte dela e ajusta. Mesma
    semente da montagem, então montar sem mexer dá as mesmas provas."""
    sessao = banco.sessao
    return selecionar(
        _ativas(db, banco),
        n_objetivas,
        n_discursivas,
        sessao.p_f,
        sessao.p_m,
        sessao.p_d,
        semente=_semente(sessao.id, "selecao", banco.revisao),
    )


def montar_provas(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    n_objetivas: int,
    n_discursivas: int,
    revisao_esperada: int,
) -> ProvasMontadas:
    """Seleção automática por tipo e faixa (o comando do orquestrador)."""
    return _montar(
        db,
        docente,
        banco,
        revisao_esperada,
        lambda: sugerir_selecao(db, banco, n_objetivas, n_discursivas),
        escolhida=False,
    )


def montar_provas_escolhidas(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    numeros_a: list[int],
    numeros_b: list[int],
    revisao_esperada: int,
) -> ProvasMontadas:
    """As questões que o docente marcou para cada prova."""
    return _montar(
        db,
        docente,
        banco,
        revisao_esperada,
        lambda: escolher(
            _ativas(db, banco),
            numeros_a,
            numeros_b,
            semente=_semente(banco.sessao_id, "selecao", banco.revisao),
        ),
        escolhida=True,
    )


def _montar(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    revisao_esperada: int,
    selecionar_questoes: Callable[[], Selecao],
    escolhida: bool,
) -> ProvasMontadas:
    # O lock serializa montagens concorrentes: a segunda espera a primeira
    # commitar e então vê as provas dela (ProvasJaMontadas, 409) em vez de
    # estourar a UniqueConstraint (500).
    travar_banco(db, banco)
    exigir_revisao(banco, revisao_esperada)
    if banco.estado is not EstadoBanco.CONGELADO:
        raise BancoNaoCongeladoException(banco.versao)
    # Não se monta prova sobre banco incoerente.
    verificar_consistencia(db, banco)

    ja_existem = list(
        db.scalars(
            select(Prova.versao).where(
                Prova.sessao_id == banco.sessao_id,
                Prova.versao.in_((VERSAO_A, VERSAO_B)),
            )
        )
    )
    if ja_existem:
        raise ProvasJaMontadasException(sorted(ja_existem))

    sessao = banco.sessao
    selecao = selecionar_questoes()

    n_objetivas_reais = sum(1 for q in selecao.a if q.tipo is TipoQuestao.OBJETIVA)
    letras_a = planejar_letras(
        n_objetivas_reais,
        sessao.k_alternativas,
        semente=_semente(sessao.id, VERSAO_A, banco.revisao, "letras"),
    )
    letras_b = planejar_letras(
        sum(1 for q in selecao.b if q.tipo is TipoQuestao.OBJETIVA),
        sessao.k_alternativas,
        semente=_semente(sessao.id, VERSAO_B, banco.revisao, "letras"),
        contra=letras_a,
    )

    prova_a = _criar_prova(db, banco, VERSAO_A, selecao.a, letras_a)
    prova_b = _criar_prova(db, banco, VERSAO_B, selecao.b, letras_b)
    sessao.estado = EstadoSessao.PROVAS_MONTADAS

    verificacao = verificar_provas(db, prova_a, prova_b)
    if verificacao.violacoes:
        # Bug do sistema: a montagem produziu o que a própria verificação
        # recusa. Desfaz — entregar isto seria pior que falhar.
        db.rollback()
        raise MontagemInconsistenteException(verificacao.violacoes)

    registrar_evento(
        db,
        TipoEventoAuditoria.PROVAS_MONTADAS,
        f"bancos_questoes:{banco.id}",
        docente.id,
        {
            "prova_a_id": prova_a.id,
            "prova_b_id": prova_b.id,
            "revisao_banco": banco.revisao,
            "n_objetivas": prova_a.n_objetivas,
            "n_discursivas": prova_a.n_discursivas,
            "escolhida_pelo_docente": escolhida,
        },
    )
    db.commit()
    return ProvasMontadas(
        prova_a_id=prova_a.id,
        prova_b_id=prova_b.id,
        revisao_banco=banco.revisao,
        compartilhadas=selecao.compartilhadas,
        sem_subtema=selecao.sem_subtema,
        verificacao=verificacao,
    )
