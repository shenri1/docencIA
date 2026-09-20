import pytest

from backend.app.domain import OrigemTexto
from backend.app.exceptions import ArquivoCorrompidoException, MaterialSemTextoException
from backend.app.services.extracao.ooxml import extrair_docx, extrair_pptx
from backend.tests.fabricas import docx_com_secoes, pptx_com_slides, zip_corrompido


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
