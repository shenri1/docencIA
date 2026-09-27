"""Exclusão e congelamento — orquestração de caso de uso.

janela de exclusões. As exclusões são aplicadas sem substituição
automática, mantendo a numeração original e marcando o item como EXCLUIDA.
relatório de impacto após CADA exclusão; o congelamento é comando
separado e irreversível — não existe descongelar.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoBanco, EstadoQuestao, EstadoSessao, EventoBanco
from backend.app.exceptions import (
    BancoCongeladoException,
    BancoVazioException,
    JanelaExclusoesFechadaException,
    NumerosInvalidosException,
)
from backend.app.models.banco import (
    BancoQuestoes,
    Questao,
    RegistroExclusao,
    RelatorioImpacto,
)
from backend.app.models.identidade import Docente
from backend.app.services.controle_banco.consistencia import verificar_consistencia
from backend.app.services.controle_banco.estado import (
    exigir_revisao,
    registrar_relatorio,
)


def _questoes_para_excluir(
    db: Session, banco: BancoQuestoes, numeros: list[int]
) -> list[Questao]:
    """Tudo-ou-nada: valida a lista inteira e só devolve se nada estiver errado.
    Aplicar metade deixaria o docente num estado que ele não pediu."""
    ativas = {
        questao.numero: questao
        for questao in db.scalars(
            select(Questao).where(
                Questao.banco_id == banco.id,
                Questao.estado == EstadoQuestao.ATIVA,
            )
        )
    }
    invalidos: list[dict[str, object]] = []
    vistos: set[int] = set()
    questoes: list[Questao] = []
    for numero in numeros:
        if numero in vistos:
            invalidos.append({"numero": numero, "motivo": "repetido na lista"})
            continue
        vistos.add(numero)
        questao = ativas.get(numero)
        if questao is None:
            invalidos.append(
                {"numero": numero, "motivo": "não existe ou não está ativa no banco"}
            )
            continue
        questoes.append(questao)
    if invalidos:
        raise NumerosInvalidosException(invalidos)
    return questoes


def excluir_questoes(
    db: Session,
    docente: Docente,
    banco: BancoQuestoes,
    numeros: list[int],
    revisao_esperada: int,
) -> RelatorioImpacto:
    exigir_revisao(banco, revisao_esperada)
    if banco.estado is EstadoBanco.CONGELADO:
        raise JanelaExclusoesFechadaException(banco.versao)
    questoes = _questoes_para_excluir(db, banco, numeros)

    for questao in questoes:
        # Marca, não apaga: o histórico de composição nunca é removido.
        questao.estado = EstadoQuestao.EXCLUIDA
        db.add(RegistroExclusao(questao_id=questao.id, docente_id=docente.id))
    banco.n_atual -= len(questoes)
    relatorio = registrar_relatorio(db, banco, EventoBanco.EXCLUSAO)
    # Um commit para a rodada inteira: exclusão pela metade não existe.
    db.commit()
    return relatorio


def congelar_banco(
    db: Session, docente: Docente, banco: BancoQuestoes, revisao_esperada: int
) -> RelatorioImpacto:
    """Fecha a janela de exclusões e a geração. Irreversível.

    `docente` entra na assinatura por simetria com `excluir_questoes` e porque o
    log de auditoria vai precisar de quem deu o comando.
    """
    exigir_revisao(banco, revisao_esperada)
    if banco.estado is EstadoBanco.CONGELADO:
        raise BancoCongeladoException(banco.versao)
    if banco.n_atual == 0:
        raise BancoVazioException(banco.versao)
    # Congelar um banco incoerente o tornaria permanentemente incoerente.
    verificar_consistencia(db, banco)

    banco.estado = EstadoBanco.CONGELADO
    banco.sessao.estado = EstadoSessao.BANCO_CONGELADO
    relatorio = registrar_relatorio(db, banco, EventoBanco.CONGELAMENTO)
    db.commit()
    return relatorio
