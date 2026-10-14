import pymupdf as fitz
import pytest

from backend.app.domain import FormatoArquivo, OrigemTexto
from backend.app.exceptions import (
    PdfMuitoLongoException,
    PdfEscaneadoOcrInsuficienteException,
    PdfProtegidoException,
)
from backend.app.services.extracao import extrair_material
from backend.app.services.extracao.ocr import ocr_disponivel
from backend.app.services.extracao.pdf import extrair_pdf
from backend.app.services.extracao.tipos import ConfigExtracao
from backend.tests.fabricas import (
    pdf_com_numeracao_impressa,
    pdf_com_texto,
    pdf_escaneado,
    pdf_escaneado_pagina_gigante,
    pdf_misto,
    pdf_protegido,
    pdf_vazio,
    txt_bytes,
)

CFG = ConfigExtracao(
    min_chars_pagina=25,
    ocr_confianca_minima=60.0,
    limiar_paginas_legiveis=0.8,
    ocr_dpi=200,
    ocr_langs="por+eng",
    ocr_max_paginas=150,
    ocr_habilitado=True,
    max_paginas=1000,
    ocr_max_megapixels=40.0,
)


class OcrFalso:
    """Dublê da interface de OCR: permite testar a regra de veredito sem
    depender do binário tesseract."""

    def __init__(self, texto: str, confianca: float) -> None:
        self.texto, self.confianca = texto, confianca

    def reconhecer(self, imagem_png: bytes, langs: str) -> tuple[str, float]:
        return self.texto, self.confianca


def test_pdf_nativo_gera_bloco_por_pagina():
    dados = pdf_com_texto(
        [
            "Primeira página com texto suficiente para o limiar de caracteres.",
            "Segunda página com texto suficiente para o limiar de caracteres.",
        ]
    )
    resultado = extrair_pdf(dados, CFG, ocr=None)
    assert [b.localizacao for b in resultado.blocos] == ["página 1", "página 2"]
    assert resultado.origem_texto is OrigemTexto.NATIVO


def test_contagem_logica_ignora_numeracao_impressa():
    """três páginas físicas, ainda que impressas como 45/46/47."""
    dados = pdf_com_numeracao_impressa(["Página 45", "Página 46", "Página 47"])
    assert extrair_pdf(dados, CFG, ocr=None).contagem_paginas_logicas == 3


def test_pdf_protegido_levanta():
    with pytest.raises(PdfProtegidoException):
        extrair_pdf(pdf_protegido(), CFG, ocr=None)


def test_pdf_escaneado_sem_ocr_disponivel_levanta():
    dados = pdf_escaneado(["Texto que só existe como imagem nesta página."])
    with pytest.raises(PdfEscaneadoOcrInsuficienteException) as erro:
        extrair_pdf(dados, CFG, ocr=None)
    assert erro.value.corpo()["paginas_afetadas"] == [1]


def test_pdf_escaneado_com_ocr_bom_e_aceito():
    dados = pdf_escaneado(["Texto que só existe como imagem nesta página."])
    ocr = OcrFalso("Texto reconhecido com qualidade suficiente para passar.", 85.0)
    resultado = extrair_pdf(dados, CFG, ocr=ocr)
    assert resultado.origem_texto is OrigemTexto.OCR
    assert resultado.blocos[0].origem is OrigemTexto.OCR


def test_pdf_escaneado_com_ocr_ruim_e_rejeitado():
    dados = pdf_escaneado(["Texto que só existe como imagem nesta página."])
    ocr = OcrFalso("Texto reconhecido com qualidade suficiente para passar.", 20.0)
    with pytest.raises(PdfEscaneadoOcrInsuficienteException):
        extrair_pdf(dados, CFG, ocr=ocr)


def test_pdf_acima_do_limite_de_ocr_e_rejeitado_sem_processar():
    dados = pdf_escaneado(["Texto em imagem A.", "Texto em imagem B."])
    cfg = ConfigExtracao(**{**CFG.__dict__, "ocr_max_paginas": 1})
    with pytest.raises(PdfEscaneadoOcrInsuficienteException) as erro:
        extrair_pdf(dados, cfg, ocr=OcrFalso("qualquer coisa", 99.0))
    assert "limite" in erro.value.corpo()["motivo"]


def test_cap_de_ocr_nao_rejeita_documento_legivel_por_nativos():
    """ocr_max_paginas limita custo, não decide legibilidade: acima do cap o
    OCR é pulado e avaliar_documento dá o veredito. 8 nativas + 2 escaneadas
    (cap=1) dão fração 0.8, que passa — origem nativa, sem blocos de OCR."""
    nativas = [
        f"Página nativa {i} com conteúdo suficiente para o limiar de caracteres."
        for i in range(8)
    ]
    escaneadas = [
        f"Página escaneada {i} que só existe como imagem nesta página."
        for i in range(2)
    ]
    dados = pdf_misto(nativas, escaneadas)
    cfg = ConfigExtracao(**{**CFG.__dict__, "ocr_max_paginas": 1})
    resultado = extrair_pdf(dados, cfg, ocr=OcrFalso("irrelevante", 99.0))
    assert resultado.origem_texto is OrigemTexto.NATIVO
    assert [b.origem for b in resultado.blocos] == [OrigemTexto.NATIVO] * 8


def test_pdf_totalmente_vazio_e_rejeitado():
    with pytest.raises(PdfEscaneadoOcrInsuficienteException):
        extrair_pdf(pdf_vazio(2), CFG, ocr=None)


def test_pdf_de_uma_pagina_com_texto_curto_e_rejeitado():
    """Uma página só com texto abaixo de min_chars_pagina não tem página
    legível: é rejeitada, listando a página afetada."""
    dados = pdf_com_texto(["curto"])
    with pytest.raises(PdfEscaneadoOcrInsuficienteException) as erro:
        extrair_pdf(dados, CFG, ocr=None)
    assert erro.value.corpo()["paginas_afetadas"] == [1]


def test_dispatcher_roteia_por_formato():
    resultado = extrair_material(
        FormatoArquivo.TXT, txt_bytes("conteúdo de teste do dispatcher"), CFG, None
    )
    assert resultado.blocos[0].texto == "conteúdo de teste do dispatcher"


@pytest.mark.skipif(not ocr_disponivel(), reason="binário tesseract ausente")
def test_ocr_real_reconhece_texto_rasterizado():
    from backend.app.services.extracao.ocr import OcrTesseract

    dados = pdf_escaneado(["RECONHECIMENTO OPTICO DE CARACTERES"], dpi=300)
    resultado = extrair_pdf(dados, CFG, ocr=OcrTesseract())
    assert "RECONHE" in resultado.blocos[0].texto.upper()


# --- Achado 3: teto de páginas e de pixels por página ---


def test_pdf_com_paginas_acima_do_teto_e_recusado_antes_de_ler():
    cfg = ConfigExtracao(**{**CFG.__dict__, "max_paginas": 3})
    with pytest.raises(PdfMuitoLongoException) as erro:
        extrair_pdf(pdf_vazio(5), cfg, ocr=None)
    assert erro.value.status_code == 413
    assert erro.value.corpo()["max_paginas"] == 3


def test_pdf_no_teto_de_paginas_e_aceito():
    cfg = ConfigExtracao(**{**CFG.__dict__, "max_paginas": 2})
    dados = pdf_com_texto(
        ["Primeira página com texto suficiente para o limiar de caracteres."] * 2
    )
    assert len(extrair_pdf(dados, cfg, ocr=None).blocos) == 2


def test_ocr_nao_renderiza_pagina_acima_do_teto_de_megapixels():
    """Pagina de 2000 pt a 300 DPI seria ~69 MP (~200 MB em RGB); o DPI é
    reduzido para a página caber no teto em vez de alocar tudo."""

    class OcrMedidor:
        pixels = 0

        def reconhecer(self, imagem_png: bytes, langs: str) -> tuple[str, float]:
            pixmap = fitz.Pixmap(imagem_png)
            OcrMedidor.pixels = pixmap.width * pixmap.height
            return "", 0.0

    cfg = ConfigExtracao(**{**CFG.__dict__, "ocr_dpi": 300, "ocr_max_megapixels": 10.0})
    with pytest.raises(PdfEscaneadoOcrInsuficienteException):
        extrair_pdf(pdf_escaneado_pagina_gigante(2000), cfg, ocr=OcrMedidor())
    assert 0 < OcrMedidor.pixels <= 10.0 * 1_000_000
