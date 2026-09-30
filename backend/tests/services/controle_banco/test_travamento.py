"""Achado 1: os comandos que movem `revisao` travam a linha do banco (FOR UPDATE)
antes de conferir a revisão, e a seguram até o commit."""

import pytest
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker

from backend.app.exceptions import RevisaoDesatualizadaException
from backend.app.models.banco import BancoQuestoes
from backend.app.services.controle_banco import exclusao_service
from backend.app.services.controle_banco.exclusao_service import (
    congelar_banco,
    excluir_questoes,
)
from backend.tests.services.controle_banco.test_exclusao_service import banco_com_dez
from backend.tests.travamento import espiar_lock


def test_excluir_segura_o_lock_da_linha_do_banco(
    db_session, docente, sessao_rascunho, engine, monkeypatch
):
    banco = banco_com_dez(db_session, sessao_rascunho)
    achados = espiar_lock(
        monkeypatch, exclusao_service, "registrar_relatorio", engine, banco.id
    )

    excluir_questoes(db_session, docente, banco, [2], banco.revisao)

    assert achados == [False]


def test_congelar_segura_o_lock_da_linha_do_banco(
    db_session, docente, sessao_rascunho, engine, monkeypatch
):
    banco = banco_com_dez(db_session, sessao_rascunho)
    achados = espiar_lock(
        monkeypatch, exclusao_service, "verificar_consistencia", engine, banco.id
    )

    congelar_banco(db_session, docente, banco, banco.revisao)

    assert achados == [False]


def test_comando_le_a_revisao_sob_o_lock_e_recusa_a_obsoleta(
    db_session, docente, sessao_rascunho, engine
):
    """A sessão guardou o banco na revisão 0; outra transação já o levou à 1.
    Sem reler sob o lock, o comando passaria com revisao_esperada=0 e 
    seria furada (lost update)."""
    banco = banco_com_dez(db_session, sessao_rascunho)
    assert banco.revisao == 0

    outra = sessionmaker(bind=engine)()
    try:
        outra.execute(
            update(BancoQuestoes).where(BancoQuestoes.id == banco.id).values(revisao=1)
        )
        outra.commit()
    finally:
        outra.close()
    assert banco.revisao == 0  # identity map obsoleto, como no caso real

    with pytest.raises(RevisaoDesatualizadaException) as erro:
        excluir_questoes(db_session, docente, banco, [2], 0)
    assert erro.value.extras["revisao_atual"] == 1
