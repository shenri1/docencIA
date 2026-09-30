"""Checagem pré-DOCX — Núcleo Determinístico.

Composição, não regra nova: cada peça já existe e já é testada nas . Todas rodam, os problemas se acumulam, e só então levanta — uma
"INCONSISTÊNCIA DE ESTADO" com a lista inteira, como verificar_consistencia faz
. NÃO é bug: é o sistema se recusando a entregar
estado incoerente.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.domain import EstadoBanco, EstadoProva, TipoGabarito
from backend.app.exceptions import InconsistenciaDeEstadoException
from backend.app.models.banco import BancoQuestoes
from backend.app.models.identidade import Docente
from backend.app.models.provas import Prova
from backend.app.services.controle_banco.consistencia import verificar_consistencia
from backend.app.services.provas.gabarito import gerar_gabarito
from backend.app.services.provas.montagem_service import VERSAO_A, VERSAO_B
from backend.app.services.provas.verificacao import verificar_provas


def verificar_exportavel(
    db: Session, docente: Docente, banco: BancoQuestoes
) -> tuple[Prova, Prova]:
    problemas: list[str] = []

    if banco.estado is not EstadoBanco.CONGELADO:
        problemas.append(f"o banco {banco.versao} não está congelado")

    try:
        verificar_consistencia(db, banco)
    except InconsistenciaDeEstadoException as erro:
        problemas.extend(erro.extras["problemas"])

    provas = {
        prova.versao: prova
        for prova in db.scalars(select(Prova).where(Prova.banco_id == banco.id))
    }
    prova_a, prova_b = provas.get(VERSAO_A), provas.get(VERSAO_B)
    if prova_a is None or prova_b is None:
        # Sem o par não há o que conferir nem o que exportar.
        problemas.append("as provas A e B não foram montadas para este banco")
        raise InconsistenciaDeEstadoException(problemas)

    for prova in (prova_a, prova_b):
        if prova.estado is not EstadoProva.MONTADA:
            problemas.append(f"a prova {prova.versao} não está montada")
        if prova.revisao_banco != banco.revisao:
            # Onde as  deixaram o bloqueio: lá é aviso, aqui não.
            problemas.append(
                f"a prova {prova.versao} está desatualizada: montada na revisão "
                f"{prova.revisao_banco}, banco na revisão {banco.revisao}"
            )

    problemas.extend(verificar_provas(db, prova_a, prova_b).violacoes)

    for prova in (prova_a, prova_b):
        gabarito = gerar_gabarito(db, docente, prova.id, TipoGabarito.COMENTADO)
        problemas.extend(f"gabarito {prova.versao}: {p}" for p in gabarito.problemas)

    if problemas:
        raise InconsistenciaDeEstadoException(problemas)
    return prova_a, prova_b
