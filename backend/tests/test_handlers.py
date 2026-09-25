import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.exceptions import (
    ArquivoCorrompidoException,
    ArquivoMuitoGrandeException,
    ArquivoProtegidoException,
    ArtefatoDeTextoInvalidoException,
    ConfiguracaoEmbeddingInvalidaException,
    CredenciaisInvalidasException,
    CredencialJaCadastradaException,
    DomainException,
    FalhaEmbeddingException,
    FalhaProvedorLLMException,
    FalhaRerankException,
    FalhaTransporteLLMException,
    FormatoNaoSuportadoException,
    IndiceNaoConfirmadoException,
    IndiceVazioException,
    MaterialDuplicadoException,
    MaterialIlegivelException,
    MaterialNaoEncontradoException,
    MaterialSemTextoException,
    NenhumPromptAtivoException,
    NenhumProvedorAtivoException,
    ParametrosInconsistentesException,
    PdfEscaneadoOcrInsuficienteException,
    PdfProtegidoException,
    PerfilInsuficienteException,
    PlaceholderNaoResolvidoException,
    PromptDivergenteException,
    RespostaLLMInvalidaException,
    SessaoEstadoInvalidaException,
    SessaoNaoEncontradaException,
    SessaoNaoIndexadaException,
    TokenInvalidoException,
    VersaoPromptDuplicadaException,
    VersaoPromptNaoEncontradaException,
)
from backend.app.handlers import registrar_exception_handlers


def _app_de_teste() -> TestClient:
    app = FastAPI()
    registrar_exception_handlers(app)

    @app.get("/levanta/credencial-duplicada")
    def _a():
        raise CredencialJaCadastradaException("123")

    @app.get("/levanta/credenciais-invalidas")
    def _b():
        raise CredenciaisInvalidasException()

    @app.get("/levanta/token-invalido")
    def _c():
        raise TokenInvalidoException()

    @app.get("/levanta/perfil-insuficiente")
    def _d():
        raise PerfilInsuficienteException()

    return TestClient(app, raise_server_exceptions=False)


def test_credencial_duplicada_retorna_409():
    client = _app_de_teste()
    resp = client.get("/levanta/credencial-duplicada")
    assert resp.status_code == 409


def test_credenciais_invalidas_retorna_401():
    client = _app_de_teste()
    resp = client.get("/levanta/credenciais-invalidas")
    assert resp.status_code == 401


def test_token_invalido_retorna_401():
    client = _app_de_teste()
    resp = client.get("/levanta/token-invalido")
    assert resp.status_code == 401


def test_perfil_insuficiente_retorna_403():
    client = _app_de_teste()
    resp = client.get("/levanta/perfil-insuficiente")
    assert resp.status_code == 403


def test_registrar_com_senha_invalida_nao_ecoa_senha_em_texto_puro(client):
    senha_curta = "abc"
    resp = client.post(
        "/auth/registrar",
        json={
            "nome": "Ana",
            "credencial_institucional": "handler001",
            "senha": senha_curta,
        },
    )
    assert resp.status_code == 422
    assert senha_curta not in resp.text


CASOS = [
    (CredencialJaCadastradaException("abc"), 409, "CREDENCIAL_JA_CADASTRADA"),
    (CredenciaisInvalidasException(), 401, "CREDENCIAIS_INVALIDAS"),
    (TokenInvalidoException(), 401, "TOKEN_INVALIDO"),
    (PerfilInsuficienteException(), 403, "PERFIL_INSUFICIENTE"),
    (ParametrosInconsistentesException(40, 40, 40), 422, "PARAMETROS_INCONSISTENTES"),
    (SessaoNaoEncontradaException(7), 404, "SESSAO_NAO_ENCONTRADA"),
    (
        SessaoEstadoInvalidaException("índice já confirmado"),
        409,
        "SESSAO_ESTADO_INVALIDO",
    ),
    (IndiceVazioException(), 409, "INDICE_VAZIO"),
    (IndiceNaoConfirmadoException(), 409, "INDICE_NAO_CONFIRMADO"),
    (MaterialNaoEncontradoException(3), 404, "MATERIAL_NAO_ENCONTRADO"),
    (MaterialDuplicadoException("P1"), 409, "MATERIAL_DUPLICADO"),
    (ArquivoMuitoGrandeException(30), 413, "ARQUIVO_MUITO_GRANDE"),
    (FormatoNaoSuportadoException("xlsx"), 415, "FORMATO_NAO_SUPORTADO"),
    (PdfProtegidoException("exige senha"), 422, "PDF_PROTEGIDO"),
    (
        PdfEscaneadoOcrInsuficienteException([2, 5], "OCR abaixo do limiar"),
        422,
        "PDF_OCR_INSUFICIENTE",
    ),
    (ArquivoProtegidoException("docx"), 422, "ARQUIVO_PROTEGIDO"),
    (ArquivoCorrompidoException("pptx"), 422, "ARQUIVO_CORROMPIDO"),
    (MaterialSemTextoException("txt"), 422, "MATERIAL_SEM_TEXTO"),
]


@pytest.mark.parametrize("exc,status,codigo", CASOS)
def test_exececoes_declaram_status_e_codigo(exc, status, codigo):
    assert isinstance(exc, DomainException)
    assert exc.status_code == status
    assert exc.codigo == codigo
    corpo = exc.corpo()
    assert corpo["detail"] and corpo["codigo"] == codigo


def test_ilegiveis_carregam_motivo():
    exc = PdfEscaneadoOcrInsuficienteException([2, 5], "OCR abaixo do limiar")
    assert isinstance(exc, MaterialIlegivelException)
    assert exc.corpo()["motivo"] == "OCR abaixo do limiar"
    assert exc.corpo()["paginas_afetadas"] == [2, 5]


def test_handler_generico_responde_qualquer_domain_exception():
    app = FastAPI()
    registrar_exception_handlers(app)

    @app.get("/levanta/duplicado")
    def _a():
        raise MaterialDuplicadoException("P1")

    cliente = TestClient(app, raise_server_exceptions=False)
    resp = cliente.get("/levanta/duplicado")
    assert resp.status_code == 409
    assert resp.json()["codigo"] == "MATERIAL_DUPLICADO"


def test_token_invalido_mantem_header_www_authenticate():
    app = FastAPI()
    registrar_exception_handlers(app)

    @app.get("/levanta/token")
    def _b():
        raise TokenInvalidoException()

    cliente = TestClient(app, raise_server_exceptions=False)
    resp = cliente.get("/levanta/token")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_falha_embedding_e_502_com_motivo():
    exc = FalhaEmbeddingException("connection refused")
    assert exc.status_code == 502
    assert exc.corpo()["codigo"] == "FALHA_EMBEDDING"
    assert exc.corpo()["motivo"] == "connection refused"


def test_falha_rerank_e_502():
    assert FalhaRerankException("timeout").status_code == 502


def test_configuracao_embedding_invalida_e_500_e_diz_as_duas_dimensoes():
    exc = ConfiguracaoEmbeddingInvalidaException(2560, 1024)
    assert exc.status_code == 500
    assert exc.corpo()["recebida"] == 2560
    assert exc.corpo()["esperada"] == 1024


def test_sessao_nao_indexada_e_409():
    assert SessaoNaoIndexadaException().status_code == 409


def test_artefato_de_texto_invalido_e_500():
    exc = ArtefatoDeTextoInvalidoException("P1")
    assert exc.status_code == 500
    assert "P1" in exc.mensagem


def test_falha_transporte_llm_e_503_com_motivo():
    exc = FalhaTransporteLLMException("ConnectError")
    assert exc.status_code == 503
    assert exc.corpo()["motivo"] == "ConnectError"


def test_falha_provedor_llm_lista_cada_provedor_tentado():
    exc = FalhaProvedorLLMException(
        [("ollama-qwen3-4b", "HTTP 500"), ("ollama-qwen3-1.7b", "ConnectError")]
    )
    assert exc.status_code == 503
    assert exc.corpo()["codigo"] == "FALHA_PROVEDOR_LLM"
    assert exc.corpo()["provedores"] == [
        {"provedor": "ollama-qwen3-4b", "motivo": "HTTP 500"},
        {"provedor": "ollama-qwen3-1.7b", "motivo": "ConnectError"},
    ]
    assert "ollama-qwen3-4b" in exc.mensagem


def test_resposta_llm_invalida_e_502_nao_503():
    # 502 e não 503 porque o provedor respondeu: o problema é o conteúdo.
    assert RespostaLLMInvalidaException("JSON malformado").status_code == 502


def test_nenhum_provedor_ativo_e_500():
    assert NenhumProvedorAtivoException().status_code == 500


def test_placeholder_nao_resolvido_e_500_e_lista_os_nomes():
    exc = PlaceholderNaoResolvidoException(["tema_escopo", "k_alternativas"])
    assert exc.status_code == 500
    assert exc.corpo()["placeholders"] == ["tema_escopo", "k_alternativas"]
    assert "tema_escopo" in exc.mensagem


def test_versao_duplicada_e_409():
    exc = VersaoPromptDuplicadaException("1.0.0")
    assert exc.status_code == 409
    assert exc.corpo()["versao"] == "1.0.0"


def test_nenhum_prompt_ativo_e_409():
    assert NenhumPromptAtivoException().status_code == 409


def test_versao_nao_encontrada_e_404():
    exc = VersaoPromptNaoEncontradaException("9.9.9")
    assert exc.status_code == 404
    assert exc.corpo()["versao"] == "9.9.9"


def test_prompt_divergente_e_409_e_traz_os_dois_hashes():
    exc = PromptDivergenteException(gravado="aaa", em_disco="bbb")
    assert exc.status_code == 409
    assert exc.corpo()["hash_gravado"] == "aaa"
    assert exc.corpo()["hash_em_disco"] == "bbb"


from backend.app.exceptions import (
    BancoCongeladoException,
    FonteInvalidaException,
    MaterialInsuficienteParaBancoException,
)


def test_material_insuficiente_e_409_e_diz_os_dois_numeros():
    exc = MaterialInsuficienteParaBancoException(chunks=12, pedidos=29)
    assert exc.status_code == 409
    assert exc.corpo()["chunks_disponiveis"] == 12
    assert exc.corpo()["questoes_pedidas"] == 29


def test_banco_congelado_e_409():
    exc = BancoCongeladoException("1.0.0")
    assert exc.status_code == 409
    assert exc.corpo()["versao"] == "1.0.0"


def test_fonte_invalida_e_502_e_lista_os_disponiveis():
    exc = FonteInvalidaException("P9", ["P1", "S2"])
    assert exc.status_code == 502
    assert exc.corpo()["identificador"] == "P9"
    assert exc.corpo()["disponiveis"] == ["P1", "S2"]


def test_parametros_banco_divergentes_e_409_e_traz_os_dois_pares():
    from backend.app.exceptions import ParametrosBancoDivergentesException

    exc = ParametrosBancoDivergentesException("v1", gravado=(10, 5), pedido=(12, 3))
    assert exc.status_code == 409
    corpo = exc.corpo()
    assert corpo["gravado"] == {"objetivas": 10, "discursivas": 5}
    assert corpo["pedido"] == {"objetivas": 12, "discursivas": 3}
