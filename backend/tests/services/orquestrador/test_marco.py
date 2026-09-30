import ast
from pathlib import Path

import backend.app.services.orquestrador as pacote_orquestrador
from backend.app.domain import (
    ComandoOrquestrador,
    EstadoBanco,
    EstadoQuestao,
    EstadoSessao,
    FaixaDificuldade,
    Marco,
)
from backend.app.services.controle_banco.estado import impacto_atual
from backend.app.services.controle_banco.exclusao_service import congelar_banco
from backend.app.services.exportacao.exportacao_service import exportar
from backend.app.services.orquestrador.marco import (
    banco_da_versao,
    marco_da_sessao,
    marco_do_banco,
)
from backend.tests.fabrica_banco import criar_banco, criar_questao_objetiva
from backend.tests.services.provas.test_gabarito import provas_montadas

P, E, A = (
    ComandoOrquestrador.PROSSEGUIR,
    ComandoOrquestrador.EXCLUIR,
    ComandoOrquestrador.AUDITAR,
)


def banco_congelado(db, docente, sessao, versao="v1"):
    """25 objetivas 7/10/8, congelado pelo serviço (com relatório)."""
    banco = criar_banco(db, sessao, versao=versao, n_objetivas=25)
    numero = 0
    for faixa, quantas in (
        (FaixaDificuldade.FACIL, 7),
        (FaixaDificuldade.MEDIA, 10),
        (FaixaDificuldade.DIFICIL, 8),
    ):
        for _ in range(quantas):
            numero += 1
            criar_questao_objetiva(
                db, banco, numero=numero, faixa=faixa, subtema=f"s{numero}"
            )
    db.commit()
    congelar_banco(db, docente, banco, banco.revisao)
    return banco


def test_sessao_em_rascunho_e_m1(db_session, sessao_rascunho):
    marco = marco_da_sessao(db_session, sessao_rascunho)
    assert marco.marco is Marco.M1_MATERIAIS
    assert marco.comandos == [P]
    assert marco.campos_prosseguir == []
    assert marco.bancos == []


def test_sessao_confirmada_sem_banco_e_m2(db_session, sessao_rascunho):
    sessao_rascunho.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    db_session.commit()
    marco = marco_da_sessao(db_session, sessao_rascunho)
    assert marco.marco is Marco.M2_BANCO
    assert marco.campos_prosseguir == ["versao", "n_objetivas", "n_discursivas"]


def test_banco_aberto_e_m3_com_lacunas_e_alerta(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=4)
    criar_questao_objetiva(db_session, banco, numero=1)
    criar_questao_objetiva(db_session, banco, numero=2)
    criar_questao_objetiva(
        db_session, banco, numero=3, estado=EstadoQuestao.EXCLUIDA
    )
    db_session.commit()

    marco = marco_do_banco(db_session, banco)
    assert marco.marco is Marco.M3_EXCLUSOES
    assert marco.motivo is None
    # Número 4 nunca foi gerado; o 3 foi excluído e não é lacuna.
    assert marco.lacunas == 1
    # Todas MEDIA contra 30/40/30: desvio muito acima de 5 pontos.
    assert marco.alerta_desvio is True
    assert marco.objetivas_ativas == 2
    assert marco.objetivas_auditadas == 0
    assert marco.comandos == [P, E, A]
    assert marco.campos_prosseguir == ["versao", "revisao_esperada"]


def test_banco_congelado_sem_provas_e_m6(db_session, docente, sessao_rascunho):
    banco = banco_congelado(db_session, docente, sessao_rascunho)
    marco = marco_do_banco(db_session, banco)
    assert marco.marco is Marco.M6_PROVAS
    assert marco.comandos == [P, A]
    assert marco.campos_prosseguir == [
        "versao",
        "revisao_esperada",
        "n_objetivas",
        "n_discursivas",
    ]


def test_provas_montadas_e_m10(db_session, docente, sessao_rascunho):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    marco = marco_do_banco(db_session, banco)
    assert marco.marco is Marco.M10_DOCX
    assert marco.campos_prosseguir == ["versao", "revisao_esperada"]


def test_exportado_e_concluido(db_session, docente, sessao_rascunho, armazenamento):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    exportar(db_session, docente, armazenamento, banco)
    marco = marco_do_banco(db_session, banco)
    assert marco.marco is Marco.CONCLUIDO
    assert marco.comandos == [A]
    assert marco.campos_prosseguir == []


def test_revisao_movida_depois_da_montagem_e_bloqueado(
    db_session, docente, sessao_rascunho
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    # É o que uma substituição aceita faz.
    banco.revisao += 1
    db_session.commit()

    marco = marco_do_banco(db_session, banco)
    assert marco.marco is Marco.BLOQUEADO
    assert "revisão" in marco.motivo
    assert marco.comandos == [A]


def test_segundo_banco_e_m3_aberto_e_bloqueado_congelado(
    db_session, docente, sessao_rascunho
):
    provas_montadas(db_session, docente, sessao_rascunho)
    segundo = criar_banco(db_session, sessao_rascunho, versao="v2", n_objetivas=1)
    criar_questao_objetiva(db_session, segundo, numero=1)
    db_session.commit()
    assert marco_do_banco(db_session, segundo).marco is Marco.M3_EXCLUSOES

    segundo.estado = EstadoBanco.CONGELADO
    db_session.commit()
    marco = marco_do_banco(db_session, segundo)
    assert marco.marco is Marco.BLOQUEADO
    assert "v1" in marco.motivo


def test_marco_da_sessao_lista_os_bancos_em_ordem(db_session, sessao_rascunho):
    sessao_rascunho.estado = EstadoSessao.MATERIAIS_CONFIRMADOS
    criar_banco(db_session, sessao_rascunho, versao="b", n_objetivas=1)
    criar_banco(db_session, sessao_rascunho, versao="a", n_objetivas=1)
    db_session.commit()
    assert [b.versao for b in marco_da_sessao(db_session, sessao_rascunho).bancos] == [
        "b",
        "a",
    ]


def test_banco_da_versao(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, versao="v1", n_objetivas=1)
    db_session.commit()
    assert banco_da_versao(db_session, sessao_rascunho, "v1") is banco
    assert banco_da_versao(db_session, sessao_rascunho, "v9") is None


def test_impacto_atual_nao_move_a_revisao(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_objetivas=1)
    criar_questao_objetiva(db_session, banco, numero=1)
    db_session.commit()
    antes = banco.revisao
    assert impacto_atual(db_session, banco).n_final == 1
    assert banco.revisao == antes


def test_orquestrador_nao_importa_provedor_nem_prompt():
    pasta = Path(pacote_orquestrador.__file__).parent
    for arquivo in pasta.glob("*.py"):
        for no in ast.walk(ast.parse(arquivo.read_text())):
            if isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith("backend.app.services.provedor"), (
                    arquivo.name
                )
                assert not no.module.startswith("backend.app.prompt"), arquivo.name
