import pytest

from backend.app.domain import EstadoBanco, EstadoQuestao, EventoBanco, NivelBloom
from backend.app.exceptions import InconsistenciaDeEstadoException
from backend.app.models.banco import Alternativa, AspectoEsperado
from backend.app.services.controle_banco.consistencia import verificar_consistencia
from backend.app.services.controle_banco.estado import registrar_relatorio
from backend.tests.fabrica_banco import (
    criar_banco,
    criar_questao_discursiva,
    criar_questao_objetiva,
)


def montar_banco_coerente(db, sessao, *, n_objetivas=2, n_discursivas=1):
    banco = criar_banco(
        db, sessao, n_objetivas=n_objetivas, n_discursivas=n_discursivas
    )
    numero = 0
    for _ in range(n_objetivas):
        numero += 1
        criar_questao_objetiva(db, banco, numero=numero)
    for _ in range(n_discursivas):
        numero += 1
        criar_questao_discursiva(db, banco, numero=numero)
    db.commit()
    return banco


def problemas_de(db, banco) -> list[str]:
    # A sessão de teste não expira objetos no commit: sem isto, as coleções
    # ainda mostrariam filhos que o teste acabou de apagar.
    db.expire_all()
    with pytest.raises(InconsistenciaDeEstadoException) as erro:
        verificar_consistencia(db, banco)
    return erro.value.extras["problemas"]


def test_banco_misto_coerente_passa(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    verificar_consistencia(db_session, banco)  # não levanta


def test_n_atual_divergente_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    banco.n_atual = 99
    db_session.commit()
    assert any("n_atual" in p for p in problemas_de(db_session, banco))


def test_questao_sem_fonte_interna_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    questao = banco.questoes[0]
    for aspecto in list(questao.aspectos):
        db_session.delete(aspecto)
    for fonte in list(questao.fontes_internas):
        db_session.delete(fonte)
    db_session.commit()
    assert any("nenhuma fonte interna" in p for p in problemas_de(db_session, banco))


def test_objetiva_com_alternativas_faltando_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    objetiva = next(q for q in banco.questoes if q.alternativas)
    db_session.delete(objetiva.alternativas[-1])
    db_session.commit()
    assert any(
        f"Q{objetiva.numero}: 4 alternativas, esperado 5" == p
        for p in problemas_de(db_session, banco)
    )


def test_objetiva_com_duas_corretas_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    objetiva = next(q for q in banco.questoes if q.alternativas)
    objetiva.alternativas[1].correta = True
    db_session.commit()
    assert any("2 alternativas corretas" in p for p in problemas_de(db_session, banco))


def test_objetiva_com_aspecto_esperado_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    objetiva = next(q for q in banco.questoes if q.alternativas)
    db_session.add(
        AspectoEsperado(
            questao_id=objetiva.id,
            ordem=1,
            texto="aspecto que não devia existir",
            fonte_interna_id=objetiva.fontes_internas[0].id,
        )
    )
    db_session.commit()
    assert any("aspectos esperados" in p for p in problemas_de(db_session, banco))


def test_objetiva_com_nivel_criar_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    objetiva = next(q for q in banco.questoes if q.alternativas)
    objetiva.nivel_bloom = NivelBloom.CRIAR
    db_session.commit()
    assert any("nível Bloom criar" in p for p in problemas_de(db_session, banco))


def test_objetiva_com_justificativa_incompleta_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    objetiva = next(q for q in banco.questoes if q.alternativas)
    objetiva.justificativa.verificacao_unicidade = None
    db_session.commit()
    assert any("verificacao_unicidade" in p for p in problemas_de(db_session, banco))


def test_discursiva_com_alternativa_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    discursiva = next(q for q in banco.questoes if q.aspectos)
    db_session.add(
        Alternativa(
            questao_id=discursiva.id, letra="A", texto="não devia existir", correta=True
        )
    )
    db_session.commit()
    assert any(
        "discursiva com 1 alternativas" in p for p in problemas_de(db_session, banco)
    )


def test_discursiva_com_um_aspecto_so_e_problema(db_session, sessao_rascunho):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    discursiva = next(q for q in banco.questoes if q.aspectos)
    db_session.delete(discursiva.aspectos[-1])
    db_session.commit()
    assert any(
        "aspectos esperados, esperado de 2 a 5" in p
        for p in problemas_de(db_session, banco)
    )


def test_discursiva_com_buraco_na_ordem_dos_aspectos_e_problema(
    db_session, sessao_rascunho
):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    discursiva = next(q for q in banco.questoes if q.aspectos)
    discursiva.aspectos[-1].ordem = 5
    db_session.commit()
    assert any("ordens dos aspectos" in p for p in problemas_de(db_session, banco))


def test_aspecto_apontando_fonte_de_outra_questao_e_problema(
    db_session, sessao_rascunho
):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    discursiva = next(q for q in banco.questoes if q.aspectos)
    alheia = next(q for q in banco.questoes if q.id != discursiva.id)
    discursiva.aspectos[0].fonte_interna_id = alheia.fontes_internas[0].id
    db_session.commit()
    assert any("fonte de outra questão" in p for p in problemas_de(db_session, banco))


def test_mais_ocupantes_de_numero_que_o_alvo_e_problema(db_session, sessao_rascunho):
    """Checagem 2c: conta ATIVA e EXCLUIDA. SUBSTITUIDA e CANDIDATA ficam fora
    — é o que permite congelar com candidata pendente."""
    banco = montar_banco_coerente(
        db_session, sessao_rascunho, n_objetivas=2, n_discursivas=0
    )
    criar_questao_objetiva(db_session, banco, numero=3)
    db_session.commit()
    assert any("ocupam número" in p for p in problemas_de(db_session, banco))


def test_candidata_pendente_nao_conta_para_o_alvo(db_session, sessao_rascunho):
    banco = montar_banco_coerente(
        db_session, sessao_rascunho, n_objetivas=2, n_discursivas=0
    )
    criar_questao_objetiva(db_session, banco, numero=1, estado=EstadoQuestao.CANDIDATA)
    db_session.commit()
    verificar_consistencia(db_session, banco)  # não levanta


def test_revisao_fora_de_sincronia_com_o_ultimo_relatorio_e_problema(
    db_session, sessao_rascunho
):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    registrar_relatorio(db_session, banco, EventoBanco.EXCLUSAO)
    banco.revisao = 7
    db_session.commit()
    assert any("último relatório" in p for p in problemas_de(db_session, banco))


def test_banco_congelado_sem_relatorio_de_congelamento_e_problema(
    db_session, sessao_rascunho
):
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    banco.estado = EstadoBanco.CONGELADO
    db_session.commit()
    assert any("congelamento" in p for p in problemas_de(db_session, banco))


def test_varios_problemas_saem_juntos(db_session, sessao_rascunho):
    """Todas as checagens rodam antes de levantar: o docente vê a lista inteira,
    não um problema por requisição."""
    banco = montar_banco_coerente(db_session, sessao_rascunho)
    banco.n_atual = 99
    banco.revisao = 7
    db_session.commit()
    problemas = problemas_de(db_session, banco)
    assert len(problemas) >= 2


def test_discursiva_com_itens_tem_de_1_a_3_aspectos_por_item(
    db_session, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_discursivas=1)
    questao = criar_questao_discursiva(db_session, banco, numero=1, aspectos=5)
    for aspecto, item in zip(questao.aspectos, (1, 1, 1, 1, 2), strict=True):
        aspecto.item = item
    db_session.commit()
    assert "Q1: item 1 com 4 aspectos, esperado de 1 a 3" in problemas_de(
        db_session, banco
    )


def test_aspectos_com_e_sem_item_na_mesma_questao(db_session, sessao_rascunho):
    banco = criar_banco(db_session, sessao_rascunho, n_discursivas=1)
    questao = criar_questao_discursiva(db_session, banco, numero=1, aspectos=2)
    questao.aspectos[0].item = 1
    db_session.commit()
    assert "Q1: aspectos com e sem item na mesma questão" in problemas_de(
        db_session, banco
    )


def test_discursiva_com_itens_e_ate_9_aspectos_e_consistente(
    db_session, sessao_rascunho
):
    banco = criar_banco(db_session, sessao_rascunho, n_discursivas=1)
    questao = criar_questao_discursiva(db_session, banco, numero=1, aspectos=6)
    for aspecto, item in zip(questao.aspectos, (1, 1, 2, 2, 3, 3), strict=True):
        aspecto.item = item
    db_session.commit()
    verificar_consistencia(db_session, banco)
