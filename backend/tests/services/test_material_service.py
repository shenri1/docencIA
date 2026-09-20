import json

import pytest

from backend.app.domain import EstadoSessao, FormatoArquivo, OrigemTexto, TipoMaterial
from backend.app.exceptions import (
    IndiceVazioException,
    MaterialDuplicadoException,
    MaterialNaoEncontradoException,
    PdfProtegidoException,
    SessaoEstadoInvalidaException,
)
from backend.app.schemas.sessao import SessaoCriar
from backend.app.services.extracao.tipos import ConfigExtracao
from backend.app.services.material_service import (
    confirmar_indice,
    listar_indice,
    registrar_material,
    remover_material,
)
from backend.app.services.sessao_service import criar_sessao
from backend.tests.fabricas import docx_com_secoes, pdf_com_texto, pdf_protegido

CFG = ConfigExtracao(
    min_chars_pagina=25,
    ocr_confianca_minima=60.0,
    limiar_paginas_legiveis=0.8,
    ocr_dpi=200,
    ocr_langs="por+eng",
    ocr_max_paginas=150,
    ocr_habilitado=False,
)
PDF = pdf_com_texto(["Conteúdo suficiente da primeira página para o limiar."])


@pytest.fixture()
def sessao(db_session, docente):
    return criar_sessao(
        db_session,
        docente,
        SessaoCriar(
            disciplina="Cálculo I",
            periodo="2026.2",
            k_alternativas=5,
            p_f=30,
            p_m=40,
            p_d=30,
        ),
    )


def _registrar(
    db,
    armazenamento,
    docente,
    sessao,
    dados=PDF,
    nome="aula.pdf",
    tipo=TipoMaterial.PDF,
):
    return registrar_material(
        db, armazenamento, docente, sessao, tipo, nome, dados, CFG, None
    )


def test_registrar_material_persiste_metadados(
    db_session, armazenamento, docente, sessao
):
    material = _registrar(db_session, armazenamento, docente, sessao)
    assert material.identificador_curto == "P1"
    assert material.formato is FormatoArquivo.PDF
    assert material.origem_texto is OrigemTexto.NATIVO
    assert material.contagem_paginas_logicas == 1
    assert material.tamanho_bytes == len(PDF)
    assert len(material.hash_sha256) == 64


def test_registrar_material_grava_arquivo_e_texto_extraido(
    db_session, armazenamento, docente, sessao
):
    material = _registrar(db_session, armazenamento, docente, sessao)
    assert material.chave_armazenamento.startswith(f"{docente.id}/{sessao.id}/")
    assert armazenamento.abrir(material.chave_armazenamento) == PDF
    artefato = json.loads(armazenamento.abrir(material.chave_texto_extraido))
    assert artefato["formato"] == "pdf"
    assert artefato["blocos"][0]["localizacao"] == "página 1"
    assert artefato["blocos"][0]["origem"] == "nativo"


def test_identificador_sequencial_por_prefixo(
    db_session, armazenamento, docente, sessao
):
    primeiro = _registrar(db_session, armazenamento, docente, sessao)
    segundo = _registrar(
        db_session,
        armazenamento,
        docente,
        sessao,
        dados=pdf_com_texto(["Outra página com conteúdo suficiente para o limiar."]),
        nome="outra.pdf",
    )
    slide = _registrar(
        db_session,
        armazenamento,
        docente,
        sessao,
        dados=docx_com_secoes([("Intro", ["parágrafo com conteúdo suficiente"])]),
        nome="slides.docx",
        tipo=TipoMaterial.SLIDE,
    )
    assert [primeiro.identificador_curto, segundo.identificador_curto] == ["P1", "P2"]
    assert slide.identificador_curto == "S1"


def test_arquivo_duplicado_na_sessao_levanta(
    db_session, armazenamento, docente, sessao
):
    _registrar(db_session, armazenamento, docente, sessao)
    with pytest.raises(MaterialDuplicadoException):
        _registrar(db_session, armazenamento, docente, sessao, nome="copia.pdf")


def test_rejeicao_nao_deixa_arquivo_nem_linha(
    db_session, armazenamento, docente, sessao
):
    with pytest.raises(PdfProtegidoException):
        _registrar(db_session, armazenamento, docente, sessao, dados=pdf_protegido())
    materiais, _ = listar_indice(db_session, sessao)
    assert materiais == []
    assert not any(armazenamento.raiz.rglob("*.pdf"))


def test_falha_no_segundo_salvar_nao_deixa_arquivo_orfao(
    db_session, armazenamento, docente, sessao, monkeypatch
):
    """Se o segundo salvar (artefato de texto) falha, o arquivo original já
    gravado deve ser removido — nada de arquivo órfão no storage."""
    salvar_original = armazenamento.salvar
    chamadas = 0

    def _salvar_falha_no_segundo(chave, dados):
        nonlocal chamadas
        chamadas += 1
        if chamadas == 2:
            raise OSError("falha simulada no segundo salvar")
        return salvar_original(chave, dados)

    monkeypatch.setattr(armazenamento, "salvar", _salvar_falha_no_segundo)

    with pytest.raises(OSError):
        _registrar(db_session, armazenamento, docente, sessao)

    assert not any(p.is_file() for p in armazenamento.raiz.rglob("*"))
    assert listar_indice(db_session, sessao)[0] == []


def test_remover_material_apaga_linha_e_arquivos(
    db_session, armazenamento, docente, sessao
):
    material = _registrar(db_session, armazenamento, docente, sessao)
    chaves = (material.chave_armazenamento, material.chave_texto_extraido)
    remover_material(db_session, armazenamento, sessao, material.id)
    assert listar_indice(db_session, sessao)[0] == []
    assert not any(armazenamento.existe(chave) for chave in chaves)


def test_remover_material_inexistente_levanta(db_session, armazenamento, sessao):
    with pytest.raises(MaterialNaoEncontradoException):
        remover_material(db_session, armazenamento, sessao, 9999)


def test_confirmar_indice_muda_estado(db_session, armazenamento, docente, sessao):
    _registrar(db_session, armazenamento, docente, sessao)
    atualizada = confirmar_indice(db_session, sessao)
    assert atualizada.estado is EstadoSessao.MATERIAIS_CONFIRMADOS
    assert listar_indice(db_session, atualizada)[1] is True


def test_confirmar_indice_vazio_levanta(db_session, sessao):
    with pytest.raises(IndiceVazioException):
        confirmar_indice(db_session, sessao)


def test_confirmar_duas_vezes_e_idempotente(db_session, armazenamento, docente, sessao):
    _registrar(db_session, armazenamento, docente, sessao)
    confirmar_indice(db_session, sessao)
    assert (
        confirmar_indice(db_session, sessao).estado
        is EstadoSessao.MATERIAIS_CONFIRMADOS
    )


def test_upload_apos_confirmacao_levanta(db_session, armazenamento, docente, sessao):
    _registrar(db_session, armazenamento, docente, sessao)
    confirmar_indice(db_session, sessao)
    with pytest.raises(SessaoEstadoInvalidaException):
        _registrar(
            db_session,
            armazenamento,
            docente,
            sessao,
            dados=pdf_com_texto(["Mais uma página com conteúdo suficiente aqui."]),
            nome="tardio.pdf",
        )


def test_upload_concorrente_com_confirmar_nao_grava_em_sessao_congelada(
    db_session, armazenamento, docente, sessao
):
    """Race: o objeto em memória ainda tem estado "rascunho" (lido antes do
    freeze), mas o banco já está congelado. O lock no início re-lê o estado e
    bloqueia o upload."""
    _registrar(db_session, armazenamento, docente, sessao)
    confirmar_indice(db_session, sessao)

    sessao.estado = EstadoSessao.RASCUNHO

    with pytest.raises(SessaoEstadoInvalidaException):
        _registrar(db_session, armazenamento, docente, sessao)

    materiais, _ = listar_indice(db_session, sessao)
    assert len(materiais) == 1


def test_remocao_apos_confirmacao_levanta(db_session, armazenamento, docente, sessao):
    material = _registrar(db_session, armazenamento, docente, sessao)
    confirmar_indice(db_session, sessao)
    with pytest.raises(SessaoEstadoInvalidaException):
        remover_material(db_session, armazenamento, sessao, material.id)


def test_nome_malicioso_nao_escapa_do_diretorio(
    db_session, armazenamento, docente, sessao
):
    material = _registrar(
        db_session, armazenamento, docente, sessao, nome="../../etc/passwd.pdf"
    )
    assert material.chave_armazenamento.startswith(f"{docente.id}/{sessao.id}/")
    assert ".." not in material.chave_armazenamento


def test_ler_com_limite_devolve_o_conteudo_quando_cabe():
    from io import BytesIO

    from backend.app.services.material_service import ler_com_limite

    assert ler_com_limite(BytesIO(b"conteudo"), 1024) == b"conteudo"


def test_ler_com_limite_rejeita_acima_do_maximo():
    from io import BytesIO

    from backend.app.exceptions import ArquivoMuitoGrandeException
    from backend.app.services.material_service import ler_com_limite

    excedente = b"x" * (2 * 1024 * 1024 + 1)
    with pytest.raises(ArquivoMuitoGrandeException) as erro:
        ler_com_limite(BytesIO(excedente), 2 * 1024 * 1024)
    assert erro.value.corpo()["max_mb"] == 2
