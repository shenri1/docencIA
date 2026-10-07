import pytest

from backend.app.domain import TipoQuestao
from backend.app.exceptions import (
    NenhumPromptAtivoException,
    PromptDivergenteException,
    VersaoPromptDuplicadaException,
    VersaoPromptNaoEncontradaException,
)
from backend.app.models.prompt_provedor import PromptMestre
from backend.app.prompt import montagem
from backend.app.prompt.montagem import (
    calcular_hash,
    carregar_modulos_versionados,
    montar_sistema,
    montar_sistema_critico,
)
from backend.app.prompt.parametros import ParametrosGeracao
from backend.app.services import prompt_mestre_service
from backend.app.services.prompt_mestre_service import (
    ativar,
    listar_versoes,
    obter_ativo,
    registrar_versao,
    verificar_integridade,
)

PARAMS = ParametrosGeracao(
    disciplina="Algoritmos",
    periodo="2026.2",
    area_do_conhecimento="Computação",
    tema_escopo="Grafos",
    k_alternativas=5,
    n_faceis=5,
    n_medias=30,
    n_dificeis=15,
)


def test_registrar_grava_o_texto_montado_e_o_hash(db_session):
    prompt = registrar_versao(db_session, "1.0.0", "docente universitário", PARAMS)
    assert prompt.conteudo == montar_sistema(TipoQuestao.OBJETIVA, PARAMS)
    assert prompt.hash_modulos == calcular_hash(carregar_modulos_versionados())
    assert prompt.criado_em is not None


def test_registrar_grava_os_quatro_textos(db_session):
    prompt = registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    assert prompt.conteudo == montar_sistema(TipoQuestao.OBJETIVA, PARAMS)
    assert prompt.conteudo_critico == montar_sistema_critico(
        TipoQuestao.OBJETIVA, PARAMS
    )
    assert prompt.conteudo_discursiva == montar_sistema(TipoQuestao.DISCURSIVA, PARAMS)
    assert prompt.conteudo_critico_discursiva == montar_sistema_critico(
        TipoQuestao.DISCURSIVA, PARAMS
    )


def test_primeira_versao_nasce_inativa(db_session):
    prompt = registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    assert prompt.ativo is False


def test_versao_duplicada_e_409(db_session):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    with pytest.raises(VersaoPromptDuplicadaException, match="1.0.0"):
        registrar_versao(db_session, "1.0.0", "papel", PARAMS)


def test_sem_versao_ativa_obter_ativo_e_409(db_session):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    with pytest.raises(NenhumPromptAtivoException):
        obter_ativo(db_session)


def test_ativar_deixa_exatamente_uma_versao_ativa(db_session):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    registrar_versao(db_session, "2.0.0", "papel", PARAMS)

    ativar(db_session, "2.0.0")
    ativar(db_session, "1.0.0")

    ativas = db_session.query(PromptMestre).filter_by(ativo=True).all()
    assert len(ativas) == 1
    assert ativas[0].versao == "1.0.0"


def test_ativar_e_idempotente(db_session):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    ativar(db_session, "1.0.0")
    ativar(db_session, "1.0.0")
    assert db_session.query(PromptMestre).filter_by(ativo=True).count() == 1


def test_ativar_versao_inexistente_e_404(db_session):
    with pytest.raises(VersaoPromptNaoEncontradaException):
        ativar(db_session, "9.9.9")


def test_listar_versoes_traz_a_mais_nova_primeiro(db_session):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    registrar_versao(db_session, "2.0.0", "papel", PARAMS)
    assert [p.versao for p in listar_versoes(db_session)] == ["2.0.0", "1.0.0"]


def test_integridade_passa_quando_o_disco_bate_com_a_versao_ativa(db_session):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    ativar(db_session, "1.0.0")
    verificar_integridade(db_session)


def test_editar_o_prompt_do_critico_sem_versao_nova_e_divergencia(
    db_session, monkeypatch
):
    prompt_mestre_service._hash_por_assinatura.cache_clear()
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    ativar(db_session, "1.0.0")
    monkeypatch.setattr(
        prompt_mestre_service,
        "carregar_modulos_versionados",
        lambda: [
            (nome, "texto editado" if nome == "critico/01_revisor.md" else conteudo)
            for nome, conteudo in montagem.carregar_modulos_versionados()
        ],
    )
    with pytest.raises(PromptDivergenteException):
        verificar_integridade(db_session)


def test_hash_do_disco_so_e_recalculado_quando_um_modulo_muda(
    db_session, monkeypatch, tmp_path
):
    registrar_versao(db_session, "1.0.0", "papel", PARAMS)
    ativar(db_session, "1.0.0")
    prompt_mestre_service._hash_por_assinatura.cache_clear()
    chamadas = []
    original = prompt_mestre_service.calcular_hash
    monkeypatch.setattr(
        prompt_mestre_service,
        "calcular_hash",
        lambda modulos: chamadas.append(1) or original(modulos),
    )

    verificar_integridade(db_session)
    verificar_integridade(db_session)
    assert len(chamadas) == 1

    novo = montagem.DIRETORIO_MODULOS / "comum" / "zz_temporario.md"
    novo.write_text("x", encoding="utf-8")
    try:
        with pytest.raises(PromptDivergenteException):
            verificar_integridade(db_session)
    finally:
        novo.unlink()
    assert len(chamadas) == 2
