import pytest

from backend.app.domain import FormatoArquivo, OrigemTexto
from backend.app.exceptions import FormatoNaoSuportadoException
from backend.app.services.extracao.tipos import (
    ClassePagina,
    ConfigExtracao,
    MetricaPagina,
    avaliar_documento,
    classificar_pagina,
    detectar_formato,
)
from backend.tests.fabricas import (
    docx_com_secoes,
    pdf_com_texto,
    pptx_com_slides,
    txt_bytes,
)

CFG = ConfigExtracao(
    min_chars_pagina=25,
    ocr_confianca_minima=60.0,
    limiar_paginas_legiveis=0.8,
    ocr_dpi=300,
    ocr_langs="por+eng",
    ocr_max_paginas=150,
    ocr_habilitado=True,
)


def test_pagina_com_texto_nativo_suficiente_e_nativa():
    metrica = MetricaPagina(numero=1, chars_nativos=100, tem_imagem=False)
    assert classificar_pagina(metrica, CFG) is ClassePagina.NATIVA


def test_pagina_sem_texto_e_sem_imagem_e_vazia():
    metrica = MetricaPagina(numero=1, chars_nativos=0, tem_imagem=False)
    assert classificar_pagina(metrica, CFG) is ClassePagina.VAZIA


def test_pagina_com_texto_curto_sem_imagem_e_vazia():
    metrica = MetricaPagina(numero=1, chars_nativos=10, tem_imagem=False)
    assert classificar_pagina(metrica, CFG) is ClassePagina.VAZIA


def test_pagina_ocr_aprovada_quando_confianca_atinge_o_minimo():
    metrica = MetricaPagina(
        numero=1, chars_nativos=0, tem_imagem=True, chars_ocr=90, confianca_ocr=72.0
    )
    assert classificar_pagina(metrica, CFG) is ClassePagina.OCR


def test_pagina_ocr_reprovada_por_confianca_baixa():
    metrica = MetricaPagina(
        numero=1, chars_nativos=0, tem_imagem=True, chars_ocr=90, confianca_ocr=30.0
    )
    assert classificar_pagina(metrica, CFG) is ClassePagina.ILEGIVEL


def test_documento_legivel_ignora_paginas_vazias_na_fracao():
    metricas = [
        MetricaPagina(numero=1, chars_nativos=100, tem_imagem=False),
        MetricaPagina(numero=2, chars_nativos=0, tem_imagem=False),
    ]
    veredito = avaliar_documento(metricas, CFG)
    assert veredito.legivel is True
    assert veredito.paginas_ilegiveis == []
    assert veredito.origem is OrigemTexto.NATIVO


def test_paginas_divisorias_sem_imagem_nao_contam_contra_o_documento():
    """Divisória de livro que só traz o número impresso ("47", 2 chars) é
    vazia: 75 nativas + 25 divisórias seguem legíveis, não viram fração 0.75."""
    metricas = [
        MetricaPagina(numero=i, chars_nativos=100, tem_imagem=False)
        for i in range(1, 76)
    ]
    metricas += [
        MetricaPagina(numero=i, chars_nativos=2, tem_imagem=False)
        for i in range(76, 101)
    ]
    assert avaliar_documento(metricas, CFG).legivel is True


def test_documento_abaixo_do_limiar_e_ilegivel_e_lista_paginas():
    metricas = [
        MetricaPagina(numero=1, chars_nativos=100, tem_imagem=False),
        MetricaPagina(numero=2, chars_nativos=0, tem_imagem=True),
        MetricaPagina(numero=3, chars_nativos=0, tem_imagem=True),
    ]
    veredito = avaliar_documento(metricas, CFG)
    assert veredito.legivel is False
    assert veredito.paginas_ilegiveis == [2, 3]


def test_origem_mista_quando_ha_nativa_e_ocr():
    metricas = [
        MetricaPagina(numero=1, chars_nativos=100, tem_imagem=False),
        MetricaPagina(
            numero=2, chars_nativos=0, tem_imagem=True, chars_ocr=90, confianca_ocr=80.0
        ),
    ]
    assert avaliar_documento(metricas, CFG).origem is OrigemTexto.MISTO


def test_documento_sem_nenhuma_pagina_util_e_ilegivel():
    metricas = [MetricaPagina(numero=1, chars_nativos=0, tem_imagem=False)]
    assert avaliar_documento(metricas, CFG).legivel is False


@pytest.mark.parametrize(
    "nome,dados,esperado",
    [
        ("aula.pdf", pdf_com_texto(["conteúdo da aula"]), FormatoArquivo.PDF),
        ("aula.docx", docx_com_secoes([("Intro", ["texto"])]), FormatoArquivo.DOCX),
        ("aula.pptx", pptx_com_slides([("Título", "corpo")]), FormatoArquivo.PPTX),
        ("aula.txt", txt_bytes("conteúdo"), FormatoArquivo.TXT),
    ],
)
def test_detectar_formato_reconhece_os_quatro(nome, dados, esperado):
    assert detectar_formato(nome, dados) is esperado


def test_detectar_formato_rejeita_extensao_fora_da_lista():
    with pytest.raises(FormatoNaoSuportadoException):
        detectar_formato("planilha.xlsx", b"PK\x03\x04")


def test_detectar_formato_rejeita_conteudo_divergente_da_extensao():
    with pytest.raises(FormatoNaoSuportadoException):
        detectar_formato("falso.pdf", pptx_com_slides([("t", "c")]))


def test_detectar_formato_rejeita_docx_que_e_pptx():
    with pytest.raises(FormatoNaoSuportadoException):
        detectar_formato("falso.docx", pptx_com_slides([("t", "c")]))
