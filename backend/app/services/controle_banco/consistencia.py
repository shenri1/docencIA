"""Checagem de consistência do banco — Núcleo Determinístico, nunca chama LLM.

Roda antes de cada leitura e antes de congelar; as 14 vão
chamá-la antes de montar provas, gabaritos e DOCX. Todas as checagens rodam e
os problemas são acumulados: o docente vê a lista inteira de uma vez.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    EventoBanco,
    NivelBloom,
    TipoQuestao,
)
from backend.app.exceptions import InconsistenciaDeEstadoException
from backend.app.models.banco import BancoQuestoes, Questao, RelatorioImpacto
from backend.app.schemas.geracao import LETRAS

# Os quatro campos que só a objetiva preenche. A discursiva grava só
# objetivo_cognitivo, e por isso eles são nullable.
_CAMPOS_JUSTIFICATIVA_OBJETIVA = (
    "justificativa_correta",
    "invalidacao_distratores",
    "verificacao_unicidade",
    "texto_verificacao_unicidade",
)

# Estados que ocupam o número de uma questão no banco. SUBSTITUIDA guarda
# histórico, CANDIDATA e DESCARTADA nunca entraram.
_OCUPANTES = (EstadoQuestao.ATIVA, EstadoQuestao.EXCLUIDA)


def _problemas_objetiva(questao: Questao, k: int, rotulo: str) -> list[str]:
    problemas: list[str] = []
    letras = sorted(a.letra for a in questao.alternativas)
    if len(letras) != k:
        problemas.append(f"{rotulo}: {len(letras)} alternativas, esperado {k}")
    elif letras != list(LETRAS[:k]):
        problemas.append(
            f"{rotulo}: letras {''.join(letras)}, esperado {LETRAS[:k]}"
        )
    corretas = [a.letra for a in questao.alternativas if a.correta]
    if len(corretas) != 1:
        problemas.append(f"{rotulo}: {len(corretas)} alternativas corretas, esperado 1")
    if questao.aspectos:
        problemas.append(
            f"{rotulo}: objetiva com {len(questao.aspectos)} aspectos esperados"
        )
    if questao.nivel_bloom is NivelBloom.CRIAR:
        problemas.append(f"{rotulo}: objetiva com nível Bloom criar")
    justificativa = questao.justificativa
    if justificativa is not None:
        faltando = [
            campo
            for campo in _CAMPOS_JUSTIFICATIVA_OBJETIVA
            if getattr(justificativa, campo) is None
        ]
        if faltando:
            problemas.append(f"{rotulo}: justificativa sem {', '.join(faltando)}")
    return problemas


def _problemas_discursiva(questao: Questao, rotulo: str) -> list[str]:
    problemas: list[str] = []
    if questao.alternativas:
        problemas.append(
            f"{rotulo}: discursiva com {len(questao.alternativas)} alternativas"
        )
    aspectos = sorted(questao.aspectos, key=lambda a: a.ordem)
    if not 2 <= len(aspectos) <= 5:
        problemas.append(
            f"{rotulo}: {len(aspectos)} aspectos esperados, esperado de 2 a 5"
        )
    ordens = [a.ordem for a in aspectos]
    if ordens != list(range(1, len(aspectos) + 1)):
        problemas.append(
            f"{rotulo}: ordens dos aspectos {ordens}, esperado 1..{len(aspectos)}"
        )
    # Aspecto tem de citar fonte DA PRÓPRIA questão: a FK não impede apontar a
    # fonte de outra, e isso quebraria a rastreabilidade.
    proprias = {f.id for f in questao.fontes_internas}
    for aspecto in aspectos:
        if aspecto.fonte_interna_id not in proprias:
            problemas.append(
                f"{rotulo}: aspecto {aspecto.ordem} aponta fonte de outra questão"
            )
    return problemas


def _problemas_da_questao(questao: Questao, k: int) -> list[str]:
    rotulo = f"Q{questao.numero}"
    problemas: list[str] = []
    if not questao.fontes_internas:
        problemas.append(f"{rotulo}: nenhuma fonte interna")
    justificativa = questao.justificativa
    if justificativa is None or not justificativa.objetivo_cognitivo:
        problemas.append(f"{rotulo}: justificativa sem objetivo cognitivo")
    if questao.tipo is TipoQuestao.OBJETIVA:
        problemas.extend(_problemas_objetiva(questao, k, rotulo))
    else:
        problemas.extend(_problemas_discursiva(questao, rotulo))
    return problemas


def verificar_consistencia(db: Session, banco: BancoQuestoes) -> None:
    """Levanta `InconsistenciaDeEstadoException` com a lista de problemas.

    NÃO é bug: é o sistema se recusando a entregar estado incoerente.
    """
    problemas: list[str] = []
    questoes = list(
        db.scalars(
            select(Questao)
            .where(Questao.banco_id == banco.id)
            .order_by(Questao.numero, Questao.id)
        )
    )
    ativas = [q for q in questoes if q.estado is EstadoQuestao.ATIVA]
    if banco.n_atual != len(ativas):
        problemas.append(
            f"n_atual = {banco.n_atual}, mas o banco tem {len(ativas)} questões ativas"
        )

    k = banco.sessao.k_alternativas
    for questao in ativas:
        problemas.extend(_problemas_da_questao(questao, k))

    for tipo, n_alvo in (
        (TipoQuestao.OBJETIVA, banco.n_alvo_objetivas),
        (TipoQuestao.DISCURSIVA, banco.n_alvo_discursivas),
    ):
        ocupantes = [
            q for q in questoes if q.tipo is tipo and q.estado in _OCUPANTES
        ]
        if len(ocupantes) > n_alvo:
            problemas.append(
                f"{len(ocupantes)} questões do tipo {tipo.value} ocupam número, "
                f"mas o banco pediu {n_alvo}"
            )

    maior_revisao = (
        db.scalar(
            select(func.max(RelatorioImpacto.revisao)).where(
                RelatorioImpacto.banco_id == banco.id
            )
        )
        or 0
    )
    if banco.revisao != maior_revisao:
        problemas.append(
            f"revisao = {banco.revisao}, mas o último relatório é da revisão "
            f"{maior_revisao}"
        )

    if banco.estado is EstadoBanco.CONGELADO:
        tem_congelamento = db.scalar(
            select(func.count())
            .select_from(RelatorioImpacto)
            .where(
                RelatorioImpacto.banco_id == banco.id,
                RelatorioImpacto.evento == EventoBanco.CONGELAMENTO,
            )
        )
        if not tem_congelamento:
            problemas.append("banco congelado sem relatório de congelamento")

    if problemas:
        raise InconsistenciaDeEstadoException(problemas)
