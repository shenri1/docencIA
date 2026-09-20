"""Extração de texto de materiais — Núcleo Determinístico, nunca chama LLM."""

from backend.app.domain import FormatoArquivo
from backend.app.services.extracao.ocr import Ocr, OcrTesseract, ocr_disponivel
from backend.app.services.extracao.ooxml import extrair_docx, extrair_pptx
from backend.app.services.extracao.pdf import extrair_pdf
from backend.app.services.extracao.tipos import (
    BlocoTexto,
    ConfigExtracao,
    ResultadoExtracao,
    detectar_formato,
)
from backend.app.services.extracao.txt import extrair_txt

__all__ = [
    "BlocoTexto",
    "ConfigExtracao",
    "Ocr",
    "OcrTesseract",
    "ResultadoExtracao",
    "detectar_formato",
    "extrair_material",
    "ocr_disponivel",
]


def extrair_material(
    formato: FormatoArquivo, dados: bytes, cfg: ConfigExtracao, ocr: Ocr | None
) -> ResultadoExtracao:
    if formato is FormatoArquivo.PDF:
        return extrair_pdf(dados, cfg, ocr)
    if formato is FormatoArquivo.DOCX:
        return extrair_docx(dados)
    if formato is FormatoArquivo.PPTX:
        return extrair_pptx(dados)
    return extrair_txt(dados)
