"""Gabarito — Núcleo Determinístico, leitura pura.

Derivado, nunca gravado: tudo que ele mostra já está persistido e aprovado, e
gravá-lo de novo seria cópia que pode divergir. A versão do gabarito é o
`revisao_banco` da prova — é assim que o "Gabarito_vZ" existe.

Nenhum LLM: depois do congelamento, renderização não chama modelo.
Texto aprovado sai como está; o que o sistema faz é não esconder o
problema — `cita_letra` e `invalidacoes_sem_letra` avisam.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.app.domain import TipoGabarito, TipoQuestao
from backend.app.models.banco import FonteInterna
from backend.app.models.identidade import Docente
from backend.app.models.provas import ItemProva
from backend.app.services.provas.leitura import letras_na_prova, obter_prova
from backend.app.services.qualidade.validador_itens import cita_letra

_MINIMO_ASPECTOS = 2


@dataclass(frozen=True)
class FonteGabarito:
    identificador_material: str
    localizacao: str
    trecho_base: str | None          # None na simples


@dataclass(frozen=True)
class InvalidacaoGabarito:
    letra: str | None                # letra DA PROVA; None quando sem vínculo
    motivo: str


@dataclass(frozen=True)
class AspectoGabarito:
    ordem: int
    texto: str
    fonte: FonteGabarito


@dataclass(frozen=True)
class ItemGabarito:
    posicao: int
    numero: int
    tipo: TipoQuestao
    letra: str | None
    fontes: list[FonteGabarito]
    aspectos: list[AspectoGabarito]
    justificativa_correta: str | None
    invalidacoes: list[InvalidacaoGabarito]
    objetivo_cognitivo: str | None
    invalidacoes_sem_letra: bool
    cita_letra: bool


@dataclass(frozen=True)
class Gabarito:
    prova_id: int
    versao: str
    modalidade: TipoGabarito
    revisao_banco: int
    desatualizada: bool
    completo: bool
    problemas: list[str]
    itens: list[ItemGabarito]


def _fonte(fonte: FonteInterna, comentado: bool) -> FonteGabarito:
    return FonteGabarito(
        identificador_material=fonte.material.identificador_curto,
        localizacao=fonte.localizacao,
        trecho_base=fonte.trecho_base if comentado else None,
    )


def _invalidacoes(
    item: ItemProva, mapa: dict[str, str]
) -> tuple[list[InvalidacaoGabarito], bool]:
    """(invalidações, sem_letra). Traduz para a letra da prova só quando o
    conjunto de letras é EXATAMENTE o das erradas originais; qualquer outra coisa
    — banco antigo, letra repetida, letra da correta — sai sem letra, na ordem
    gravada. Adivinhar qual motivo é de qual alternativa seria pior que não dizer.
    """
    gravadas = item.questao.justificativa.invalidacao_distratores or []
    erradas = sorted(a.letra for a in item.questao.alternativas if not a.correta)
    ligadas = all(isinstance(g, dict) for g in gravadas) and sorted(
        g["letra"] for g in gravadas
    ) == erradas
    if not ligadas:
        motivos = [g["motivo"] if isinstance(g, dict) else g for g in gravadas]
        return [InvalidacaoGabarito(None, motivo) for motivo in motivos], True
    traduzidas = [InvalidacaoGabarito(mapa[g["letra"]], g["motivo"]) for g in gravadas]
    return sorted(traduzidas, key=lambda i: i.letra), False


def _item(item: ItemProva, comentado: bool) -> ItemGabarito:
    questao = item.questao
    justificativa = questao.justificativa
    fontes = [_fonte(f, comentado) for f in questao.fontes_internas]

    if questao.tipo is TipoQuestao.DISCURSIVA:
        return ItemGabarito(
            posicao=item.posicao,
            numero=questao.numero,
            tipo=questao.tipo,
            letra=None,
            fontes=fontes,
            aspectos=[
                AspectoGabarito(a.ordem, a.texto, _fonte(a.fonte, comentado))
                for a in sorted(questao.aspectos, key=lambda a: a.ordem)
            ],
            justificativa_correta=None,
            invalidacoes=[],
            objetivo_cognitivo=justificativa.objetivo_cognitivo if comentado else None,
            invalidacoes_sem_letra=False,
            cita_letra=False,
        )

    if not comentado:
        return ItemGabarito(
            posicao=item.posicao,
            numero=questao.numero,
            tipo=questao.tipo,
            letra=item.letra_atribuida,
            fontes=fontes,
            aspectos=[],
            justificativa_correta=None,
            invalidacoes=[],
            objetivo_cognitivo=None,
            invalidacoes_sem_letra=False,
            # A simples não mostra texto livre: o aviso não tem a que se referir.
            cita_letra=False,
        )

    invalidacoes, sem_letra = _invalidacoes(item, letras_na_prova(item))
    textos = [justificativa.justificativa_correta or ""] + [
        i.motivo for i in invalidacoes
    ]
    return ItemGabarito(
        posicao=item.posicao,
        numero=questao.numero,
        tipo=questao.tipo,
        letra=item.letra_atribuida,
        fontes=fontes,
        aspectos=[],
        justificativa_correta=justificativa.justificativa_correta,
        invalidacoes=invalidacoes,
        objetivo_cognitivo=justificativa.objetivo_cognitivo,
        invalidacoes_sem_letra=sem_letra,
        cita_letra=any(cita_letra(texto) for texto in textos),
    )


def _problemas(itens: list[ItemGabarito], k: int, comentado: bool) -> list[str]:
    """Critério da gabarito para 100% das questões selecionadas. Com as
     funcionando a lista é vazia; ela existe porque critério de
    aceitação que não é medido é suposição."""
    problemas: list[str] = []
    for item in itens:
        rotulo = f"posição {item.posicao}"
        if item.tipo is TipoQuestao.OBJETIVA:
            if item.letra is None:
                problemas.append(f"{rotulo}: objetiva sem letra atribuída")
            if not any(f.localizacao for f in item.fontes):
                problemas.append(f"{rotulo}: objetiva sem fonte com localização")
            if comentado and not item.justificativa_correta:
                problemas.append(f"{rotulo}: sem justificativa da correta")
            if comentado and len(item.invalidacoes) != k - 1:
                problemas.append(
                    f"{rotulo}: {len(item.invalidacoes)} invalidações, esperado {k - 1}"
                )
        else:
            if len(item.aspectos) < _MINIMO_ASPECTOS:
                problemas.append(
                    f"{rotulo}: {len(item.aspectos)} aspectos esperados, mínimo "
                    f"{_MINIMO_ASPECTOS}"
                )
            if any(not a.fonte.localizacao for a in item.aspectos):
                problemas.append(f"{rotulo}: aspecto sem fonte com localização")
            if comentado and not item.objetivo_cognitivo:
                problemas.append(f"{rotulo}: sem objetivo cognitivo")
    return problemas


def gerar_gabarito(
    db: Session, docente: Docente, prova_id: int, modalidade: TipoGabarito
) -> Gabarito:
    prova = obter_prova(db, docente, prova_id)
    comentado = modalidade is TipoGabarito.COMENTADO
    itens = [
        _item(item, comentado) for item in sorted(prova.itens, key=lambda i: i.posicao)
    ]
    problemas = _problemas(itens, prova.sessao.k_alternativas, comentado)
    return Gabarito(
        prova_id=prova.id,
        versao=prova.versao,
        modalidade=modalidade,
        revisao_banco=prova.revisao_banco,
        # Gera normalmente: a questão substituída continua gravada, então o
        # gabarito segue fiel à prova impressa. Quem bloqueia é.
        desatualizada=prova.revisao_banco != prova.banco.revisao,
        completo=not problemas,
        problemas=problemas,
        itens=itens,
    )
