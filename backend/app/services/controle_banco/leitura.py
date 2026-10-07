"""Leitura do banco — Núcleo Determinístico, nunca chama LLM.

entrega em blocos e sem gabarito salvo pedido explícito.
O que NÃO existe aqui é tão importante quanto o que existe: nenhum dataclass
tem campo para `JustificativaEstruturada` ou `RevisaoQuestao.rascunho`, e por
isso vazar esses dados exigiria mudar o modelo de leitura, não esquecer um
`exclude`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.domain import (
    EstadoBanco,
    EstadoQuestao,
    FaixaDificuldade,
    NivelBloom,
    TipoQuestao,
)
from backend.app.models.banco import (
    AspectoEsperado,
    FonteInterna,
    Questao,
    RelatorioImpacto,
)
from backend.app.models.identidade import Docente
from backend.app.services.controle_banco.consistencia import verificar_consistencia
from backend.app.services.controle_banco.estado import obter_banco

# Por padrão o docente vê o banco, não o histórico: a ocupante do número e as
# que ele excluiu.
_ESTADOS_PADRAO = (EstadoQuestao.ATIVA, EstadoQuestao.EXCLUIDA)


@dataclass(frozen=True)
class FonteLida:
    identificador_material: str
    localizacao: str
    trecho_base: str


@dataclass(frozen=True)
class AlternativaLida:
    letra: str
    texto: str


@dataclass(frozen=True)
class AspectoLido:
    ordem: int
    texto: str
    fonte: FonteLida


@dataclass(frozen=True)
class QuestaoLida:
    numero: int
    tipo: TipoQuestao
    estado: EstadoQuestao
    faixa_dificuldade: FaixaDificuldade
    nivel_bloom: NivelBloom
    tema: str | None
    enunciado: str
    fontes: list[FonteLida]
    # Violações que sobreviveram à revisão: é por elas que o docente
    # sabe quais questões olhar antes de excluir.
    violacoes: list[dict]
    alternativas: list[AlternativaLida]
    letra_correta: str | None
    aspectos_esperados: list[AspectoLido]


@dataclass(frozen=True)
class BancoLido:
    banco_id: int
    versao: str
    revisao: int
    rotulo: str
    estado: EstadoBanco
    n_alvo: int
    n_alvo_objetivas: int
    n_alvo_discursivas: int
    n_atual: int
    ultimo_relatorio: RelatorioImpacto | None
    questoes: list[QuestaoLida]


def _fonte_lida(fonte: FonteInterna) -> FonteLida:
    return FonteLida(
        identificador_material=fonte.material.identificador_curto,
        localizacao=fonte.localizacao,
        trecho_base=fonte.trecho_base,
    )


def _aspecto_lido(aspecto: AspectoEsperado) -> AspectoLido:
    return AspectoLido(
        ordem=aspecto.ordem, texto=aspecto.texto, fonte=_fonte_lida(aspecto.fonte)
    )


def questao_lida(questao: Questao, com_gabarito: bool) -> QuestaoLida:
    alternativas = sorted(questao.alternativas, key=lambda a: a.letra)
    aspectos = sorted(questao.aspectos, key=lambda a: a.ordem)
    correta = next((a.letra for a in alternativas if a.correta), None)
    return QuestaoLida(
        numero=questao.numero,
        tipo=questao.tipo,
        estado=questao.estado,
        faixa_dificuldade=questao.faixa_dificuldade,
        nivel_bloom=questao.nivel_bloom,
        tema=questao.tema,
        enunciado=questao.enunciado,
        fontes=[_fonte_lida(f) for f in questao.fontes_internas],
        violacoes=list(questao.revisao.violacoes_final) if questao.revisao else [],
        alternativas=[AlternativaLida(a.letra, a.texto) for a in alternativas],
        # Os aspectos são o equivalente discursivo do gabarito, e seguem a mesma
        # regra.
        letra_correta=correta if com_gabarito else None,
        aspectos_esperados=[_aspecto_lido(a) for a in aspectos] if com_gabarito else [],
    )


def ler_banco(
    db: Session,
    docente: Docente,
    banco_id: int,
    de: int,
    ate: int,
    com_gabarito: bool,
    incluir_historico: bool,
) -> BancoLido:
    banco = obter_banco(db, docente, banco_id)
    # Recusa-se a entregar estado incoerente antes de montar a resposta.
    verificar_consistencia(db, banco)
    estados = tuple(EstadoQuestao) if incluir_historico else _ESTADOS_PADRAO
    questoes = db.scalars(
        select(Questao)
        .where(
            Questao.banco_id == banco.id,
            Questao.numero >= de,
            Questao.numero <= ate,
            Questao.estado.in_(estados),
        )
        .options(
            selectinload(Questao.alternativas),
            selectinload(Questao.fontes_internas).selectinload(FonteInterna.material),
            selectinload(Questao.revisao),
            selectinload(Questao.aspectos)
            .selectinload(AspectoEsperado.fonte)
            .selectinload(FonteInterna.material),
        )
        .order_by(Questao.numero, Questao.id)
    )
    ultimo = db.scalar(
        select(RelatorioImpacto)
        .where(RelatorioImpacto.banco_id == banco.id)
        .order_by(RelatorioImpacto.revisao.desc(), RelatorioImpacto.id.desc())
        .limit(1)
    )
    return BancoLido(
        banco_id=banco.id,
        versao=banco.versao,
        revisao=banco.revisao,
        rotulo=f"{banco.versao}.r{banco.revisao}",
        estado=banco.estado,
        n_alvo=banco.n_alvo,
        n_alvo_objetivas=banco.n_alvo_objetivas,
        n_alvo_discursivas=banco.n_alvo_discursivas,
        n_atual=banco.n_atual,
        ultimo_relatorio=ultimo,
        questoes=[questao_lida(q, com_gabarito) for q in questoes],
    )


def listar_relatorios(
    db: Session, docente: Docente, banco_id: int
) -> list[RelatorioImpacto]:
    banco = obter_banco(db, docente, banco_id)
    return list(
        db.scalars(
            select(RelatorioImpacto)
            .where(RelatorioImpacto.banco_id == banco.id)
            .order_by(RelatorioImpacto.revisao, RelatorioImpacto.id)
        )
    )
