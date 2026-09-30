import pytest

from backend.app.core.config import settings

from backend.app.domain import OrigemTexto
from backend.app.exceptions import (
    ArquivoCorrompidoException,
    ArquivoDescompressaoExcessivaException,
    MaterialSemTextoException,
)
from backend.app.services.extracao.ooxml import extrair_docx, extrair_pptx
from backend.tests.fabricas import (
    docx_com_secoes,
    docx_com_tabela,
    pptx_com_slides,
    zip_corrompido,
    zip_ooxml_com_entradas,
)


def test_docx_localiza_por_secao_e_paragrafo():
    dados = docx_com_secoes(
        [("Introdução", ["primeiro parágrafo", "segundo parágrafo"])]
    )
    resultado = extrair_docx(dados)
    assert resultado.blocos[0].localizacao == "Introdução · par. 1"
    assert resultado.blocos[1].localizacao == "Introdução · par. 2"
    assert resultado.blocos[0].texto == "primeiro parágrafo"
    assert resultado.blocos[0].origem is OrigemTexto.NATIVO


def test_docx_nao_tem_contagem_de_paginas():
    dados = docx_com_secoes([("Intro", ["texto do parágrafo"])])
    assert extrair_docx(dados).contagem_paginas_logicas is None


def test_docx_vazio_levanta_sem_texto():
    with pytest.raises(MaterialSemTextoException):
        extrair_docx(docx_com_secoes([]))


def test_docx_extrai_texto_de_tabela():
    dados = docx_com_tabela([["nome", "nota"], ["ana", "9.5"], ["bruno", "8.0"]])
    resultado = extrair_docx(dados)
    assert [b.localizacao for b in resultado.blocos] == ["tabela 1"]
    assert "ana" in resultado.blocos[0].texto
    assert "9.5" in resultado.blocos[0].texto
    assert resultado.blocos[0].origem is OrigemTexto.NATIVO


def test_docx_corrompido_levanta():
    with pytest.raises(ArquivoCorrompidoException):
        extrair_docx(zip_corrompido())


def test_pptx_conta_slides_e_localiza_por_slide():
    dados = pptx_com_slides([("Título A", "corpo A"), ("Título B", "corpo B")])
    resultado = extrair_pptx(dados)
    assert resultado.contagem_paginas_logicas == 2
    assert [b.localizacao for b in resultado.blocos] == ["slide 1", "slide 2"]
    assert "Título A" in resultado.blocos[0].texto
    assert "corpo A" in resultado.blocos[0].texto


def test_pptx_inclui_notas_do_orador():
    dados = pptx_com_slides([("T", "corpo")], notas="lembrar de citar a fonte")
    assert "lembrar de citar a fonte" in extrair_pptx(dados).blocos[0].texto


def test_pptx_sem_texto_levanta():
    with pytest.raises(MaterialSemTextoException):
        extrair_pptx(pptx_com_slides([]))


def test_pptx_corrompido_levanta():
    with pytest.raises(ArquivoCorrompidoException):
        extrair_pptx(zip_corrompido())


# --- Achado 2: MAX_UPLOAD_MB limita o comprimido; o descomprimido tem teto próprio ---


@pytest.mark.parametrize("extrair", [extrair_docx, extrair_pptx])
def test_ooxml_com_descompressao_acima_do_teto_e_recusado(monkeypatch, extrair):
    monkeypatch.setattr(settings, "max_ooxml_descomprimido_mb", 1)
    bomba = zip_ooxml_com_entradas({"word/document.xml": b"0" * (3 * 1024 * 1024)})
    assert len(bomba) < 100 * 1024  # cabe folgado em MAX_UPLOAD_MB
    with pytest.raises(ArquivoDescompressaoExcessivaException) as erro:
        extrair(bomba)
    assert erro.value.status_code == 413


@pytest.mark.parametrize("extrair", [extrair_docx, extrair_pptx])
def test_ooxml_com_entradas_demais_e_recusado(monkeypatch, extrair):
    monkeypatch.setattr(settings, "max_ooxml_entradas", 5)
    muitas = zip_ooxml_com_entradas({f"parte{i}.xml": b"<a/>" for i in range(10)})
    with pytest.raises(ArquivoDescompressaoExcessivaException):
        extrair(muitas)


def test_docx_dentro_do_teto_continua_sendo_extraido(monkeypatch):
    monkeypatch.setattr(settings, "max_ooxml_descomprimido_mb", 50)
    dados = docx_com_secoes([("Intro", ["texto do parágrafo"])])
    assert extrair_docx(dados).blocos
