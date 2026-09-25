"""Laço do banco — orquestração de caso de uso.

O commit é por questão, não por banco. Cada questão custa duas chamadas ao
modelo (Gerador + Crítico), cerca de 38 s; falha no meio preserva o que já foi
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
    RevisaoQuestao,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.schemas.geracao import LETRAS
from backend.app.services.calculo_distribuicao_service import calcular_distribuicao
from backend.app.services.critico.agente_critico_service import (
    ResultadoRevisao,
    item_de,
    revisar_questao,
)
from backend.app.services.geracao.agente_gerador_service import (
    ResultadoGeracao,
    gerar_questao,
)
from backend.app.services.geracao.ancoras import selecionar_ancoras
from backend.app.services.geracao.contexto import resolver_fontes
from backend.app.services.prompt_mestre_service import verificar_integridade
from backend.app.services.qualidade.validador_itens import Violacao, validar_item
from backend.app.services.sessao_service import exigir_indice_confirmado


@dataclass(frozen=True)
class AncoraImprodutiva:
    numero: int
    localizacao: str
    motivo: str


@dataclass(frozen=True)
class ItemComViolacao:
    numero: int
    violacoes: list[Violacao]


@dataclass(frozen=True)
class ResumoBanco:
    banco_id: int
    geradas: int
    ja_existentes: int
    improdutivas: list[AncoraImprodutiva]
    # Violações que sobreviveram à revisão. É por aqui que o docente sabe
    # quais questões olhar antes da janela de exclusões.
    com_violacoes: list[ItemComViolacao]


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
    faixa: FaixaDificuldade,
    resultado: ResultadoGeracao,
    revisao: ResultadoRevisao,
    violacoes_rascunho: list[Violacao],
    violacoes_final: list[Violacao],
) -> None:
    final = revisao.questao
    # Antes de qualquer db.add: fonte inválida levanta sem deixar objeto
    # pendente na sessão. Só a versão revisada vira FonteInterna.
    fontes = resolver_fontes(final.fontes, resultado.trechos)

    questao = Questao(
        banco_id=banco.id,
        numero=resultado.numero,
        enunciado=final.enunciado,
        nivel_bloom=final.nivel_bloom,
        # A faixa vem do plano, não do modelo: o código já a conhece.
        faixa_dificuldade=faixa,
        tema=final.tema,
        estado=EstadoQuestao.ATIVA,
    )
    db.add(questao)
    db.flush()  # precisa do id para os filhos

    for letra, alternativa in zip(LETRAS, final.alternativas, strict=False):
        db.add(
            Alternativa(
                questao_id=questao.id,
                letra=letra,
                texto=alternativa.texto,
                correta=letra == final.letra_correta,
                e_gemeo_malvado=alternativa.e_gemeo_malvado,
            )
        )
    for material_id, localizacao, trecho in fontes:
        db.add(
            FonteInterna(
                questao_id=questao.id,
                material_id=material_id,
                localizacao=localizacao,
                trecho_base=trecho,
            )
        )
    justificativa = final.justificativa
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
    db.add(
        RevisaoQuestao(
            questao_id=questao.id,
            rascunho=resultado.questao.model_dump(mode="json"),
            violacoes_rascunho=[v.como_dict() for v in violacoes_rascunho],
            violacoes_final=[v.como_dict() for v in violacoes_final],
            modelo_geracao=resultado.modelo,
            modelo_revisao=revisao.modelo,
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
    com_violacoes: list[ItemComViolacao] = []
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

        # o determinístico mede, o semântico revisa com essa medida
        # como feedback, e o determinístico mede de novo.
        violacoes_rascunho = validar_item(item_de(resultado.questao, resultado.trechos))
        revisao = revisar_questao(
            provedor,
            sessao,
            resultado.trechos,
            resultado.questao,
            violacoes_rascunho,
            faixa,
            distribuicao,
        )
        if revisao.questao is None:
            # O crítico concluiu que o material não sustenta a questão: 
            # funcionando. Nada é persistido, e a retomada tenta de novo.
            improdutivas.append(
                AncoraImprodutiva(
                    numero=numero,
                    localizacao=resultado.localizacao_ancora,
                    motivo="revisão: "
                    + (revisao.motivo_insuficiencia or "sem motivo declarado"),
                )
            )
            continue

        violacoes_final = validar_item(item_de(revisao.questao, resultado.trechos))
        _persistir(
            db,
            banco,
            faixa,
            resultado,
            revisao,
            violacoes_rascunho,
            violacoes_final,
        )
        geradas += 1
        if violacoes_final:
            com_violacoes.append(ItemComViolacao(numero, violacoes_final))

    return ResumoBanco(
        banco_id=banco.id,
        geradas=geradas,
        ja_existentes=len(ja_existentes),
        improdutivas=improdutivas,
        com_violacoes=com_violacoes,
    )
