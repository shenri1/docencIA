"""Laço do banco — orquestração de caso de uso.

O commit é por questão, não por banco. 29 questões custam ~9 minutos (medido:
19,1s cada com oito trechos reais); falha no minuto 7 preserva o que já foi
gerado, e chamar de novo continua de onde parou.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoBanco, EstadoQuestao, FaixaDificuldade
from backend.app.exceptions import BancoCongeladoException
from backend.app.models.banco import (
    Alternativa,
    BancoQuestoes,
    FonteInterna,
    JustificativaEstruturada,
    Questao,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.schemas.geracao import LETRAS
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.geracao.agente_gerador_service import (
    ResultadoGeracao,
    gerar_questao,
)
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.prompt_mestre_service import verificar_integridade
from backend.app.services.sessao_service import exigir_indice_confirmado


@dataclass(frozen=True)
class AncoraImprodutiva:
    numero: int
    localizacao: str
    motivo: str


@dataclass(frozen=True)
class ResumoBanco:
    banco_id: int
    geradas: int
    ja_existentes: int
    improdutivas: list[AncoraImprodutiva]


def _obter_ou_criar_banco(
    db: Session, sessao: SessaoGeracao, versao: str, n_alvo: int
) -> BancoQuestoes:
    banco = db.scalar(
        select(BancoQuestoes).where(
            BancoQuestoes.sessao_id == sessao.id, BancoQuestoes.versao == versao
        )
    )
    if banco is None:
        banco = BancoQuestoes(
            sessao_id=sessao.id, versao=versao, n_alvo=n_alvo, n_atual=0
        )
        db.add(banco)
        db.commit()
        db.refresh(banco)
    elif banco.estado is EstadoBanco.CONGELADO:
        # congelado não recebe questão nova.
        raise BancoCongeladoException(versao)
    return banco


def _persistir(
    db: Session,
    banco: BancoQuestoes,
    resultado: ResultadoGeracao,
    faixa: FaixaDificuldade,
) -> None:
    gerada = resultado.questao
    questao = Questao(
        banco_id=banco.id,
        numero=resultado.numero,
        enunciado=gerada.enunciado,
        nivel_bloom=gerada.nivel_bloom,
        # A faixa vem do plano, não do modelo: o código já a conhece.
        faixa_dificuldade=faixa,
        tema=gerada.tema,
        estado=EstadoQuestao.ATIVA,
    )
    db.add(questao)
    db.flush()  # precisa do id para os filhos

    for letra, alternativa in zip(LETRAS, gerada.alternativas, strict=False):
        db.add(
            Alternativa(
                questao_id=questao.id,
                letra=letra,
                texto=alternativa.texto,
                correta=letra == gerada.letra_correta,
                e_gemeo_malvado=alternativa.e_gemeo_malvado,
            )
        )
    for material_id, localizacao, trecho in resultado.fontes_resolvidas:
        db.add(
            FonteInterna(
                questao_id=questao.id,
                material_id=material_id,
                localizacao=localizacao,
                trecho_base=trecho,
            )
        )
    justificativa = gerada.justificativa
    db.add(
        JustificativaEstruturada(
            questao_id=questao.id,
            objetivo_cognitivo=justificativa.objetivo_cognitivo,
            justificativa_correta=justificativa.justificativa_correta,
            invalidacao_distratores=list(justificativa.invalidacao_distratores),
            verificacao_unicidade=justificativa.verificacao_unicidade,
            texto_verificacao_unicidade=justificativa.texto_verificacao_unicidade,
        )
    )
    banco.n_atual += 1
    db.commit()


def gerar_banco(
    db: Session,
    embeddings,
    reranker,
    provedor,
    sessao: SessaoGeracao,
    n_alvo: int,
    versao: str,
) -> ResumoBanco:
    # Verificações baratas primeiro: descobrir material insuficiente no minuto
    # 7 desperdiçaria minutos de GPU.
    verificar_integridade(db)
    exigir_indice_confirmado(sessao)
    distribuicao = calcular_distribuicao(n_alvo, sessao.p_f, sessao.p_m, sessao.p_d)
    banco = _obter_ou_criar_banco(db, sessao, versao, n_alvo)
    ancoras = selecionar_ancoras(db, sessao, n_alvo)

    # numero == índice da âncora + 1. Como a seleção é determinística,
    # recalcular dá sempre a mesma lista, e retomar é pular os que já existem.
    plano: list[tuple[int, FaixaDificuldade]] = []
    for faixa, quantidade in distribuicao.itens():
        # `base` é ligado ANTES do extend: usar len(plano) dentro do gerador o
        # avaliaria enquanto a lista já cresce, gerando números repetidos
        # ([1, 3, 5, 4, 6, 8, 10, 8, ...]) que violariam a unique constraint.
        base = len(plano)
        plano.extend((base + i + 1, faixa) for i in range(quantidade))

    ja_existentes = set(
        db.scalars(select(Questao.numero).where(Questao.banco_id == banco.id))
    )

    geradas = 0
    improdutivas: list[AncoraImprodutiva] = []
    for numero, faixa in plano:
        if numero in ja_existentes:
            continue
        resultado = gerar_questao(
            db,
            embeddings,
            reranker,
            provedor,
            sessao,
            ancoras[numero - 1],
            faixa,
            numero,
            distribuicao,
        )
        if resultado.questao is None:
            improdutivas.append(
                AncoraImprodutiva(
                    numero=numero,
                    localizacao=resultado.localizacao_ancora,
                    motivo=resultado.motivo_insuficiencia or "sem motivo declarado",
                )
            )
            continue
        _persistir(db, banco, resultado, faixa)
        geradas += 1

    return ResumoBanco(
        banco_id=banco.id,
        geradas=geradas,
        ja_existentes=len(ja_existentes),
        improdutivas=improdutivas,
    )
