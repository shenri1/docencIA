import zipfile
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from pathlib import Path

from backend.app.core.config import settings
from backend.app.domain import FormatoArquivo, OrigemTexto
from backend.app.exceptions import FormatoNaoSuportadoException


@dataclass(frozen=True)
class BlocoTexto:
    localizacao: str
    texto: str
    origem: OrigemTexto


@dataclass(frozen=True)
class ResultadoExtracao:
    blocos: list[BlocoTexto]
    contagem_paginas_logicas: int | None
    origem_texto: OrigemTexto


@dataclass(frozen=True)
class MetricaPagina:
    numero: int
    chars_nativos: int
    tem_imagem: bool
    chars_ocr: int = 0
    confianca_ocr: float = 0.0


class ClassePagina(str, Enum):
    NATIVA = "nativa"
    OCR = "ocr"
    VAZIA = "vazia"
    ILEGIVEL = "ilegivel"


@dataclass(frozen=True)
class VereditoDocumento:
    legivel: bool
    paginas_ilegiveis: list[int]
    origem: OrigemTexto


@dataclass(frozen=True)
class ConfigExtracao:
    min_chars_pagina: int
    ocr_confianca_minima: float
    limiar_paginas_legiveis: float
    ocr_dpi: int
    ocr_langs: str
    ocr_max_paginas: int
    ocr_habilitado: bool

    @classmethod
    def das_settings(cls) -> ConfigExtracao:
        return cls(
            min_chars_pagina=settings.min_chars_pagina,
            ocr_confianca_minima=settings.ocr_confianca_minima,
            limiar_paginas_legiveis=settings.limiar_paginas_legiveis,
            ocr_dpi=settings.ocr_dpi,
            ocr_langs=settings.ocr_langs,
            ocr_max_paginas=settings.ocr_max_paginas,
            ocr_habilitado=settings.ocr_enabled,
        )


def classificar_pagina(metrica: MetricaPagina, cfg: ConfigExtracao) -> ClassePagina:
    if metrica.chars_nativos >= cfg.min_chars_pagina:
        return ClassePagina.NATIVA
    if (
        metrica.chars_ocr >= cfg.min_chars_pagina
        and metrica.confianca_ocr >= cfg.ocr_confianca_minima
    ):
        return ClassePagina.OCR
    # Vazia só quando não há texto algum: uma página com texto curto (abaixo
    # de min_chars_pagina) tem conteúdo real e conta como ilegível, em vez de
    # sumir do veredito — senão um PDF com texto curto seria tratado como
    # "sem páginas" enquanto um TXT equivalente passaria.
    if metrica.chars_nativos == 0 and not metrica.tem_imagem:
        return ClassePagina.VAZIA
    return ClassePagina.ILEGIVEL


def avaliar_documento(
    metricas: list[MetricaPagina], cfg: ConfigExtracao
) -> VereditoDocumento:
    classes = {m.numero: classificar_pagina(m, cfg) for m in metricas}
    nao_vazias = [n for n, c in classes.items() if c is not ClassePagina.VAZIA]
    legiveis = [
        n for n, c in classes.items() if c in (ClassePagina.NATIVA, ClassePagina.OCR)
    ]
    ilegiveis = sorted(n for n, c in classes.items() if c is ClassePagina.ILEGIVEL)

    if not nao_vazias:
        return VereditoDocumento(False, ilegiveis, OrigemTexto.NATIVO)

    fracao = len(legiveis) / len(nao_vazias)
    tem_nativa = any(classes[n] is ClassePagina.NATIVA for n in legiveis)
    tem_ocr = any(classes[n] is ClassePagina.OCR for n in legiveis)
    if tem_nativa and tem_ocr:
        origem = OrigemTexto.MISTO
    elif tem_ocr:
        origem = OrigemTexto.OCR
    else:
        origem = OrigemTexto.NATIVO
    return VereditoDocumento(fracao >= cfg.limiar_paginas_legiveis, ilegiveis, origem)


_EXTENSOES = {
    ".pdf": FormatoArquivo.PDF,
    ".pptx": FormatoArquivo.PPTX,
    ".docx": FormatoArquivo.DOCX,
    ".txt": FormatoArquivo.TXT,
}
_PREFIXO_OOXML = {FormatoArquivo.DOCX: "word/", FormatoArquivo.PPTX: "ppt/"}


def detectar_formato(nome_arquivo: str, dados: bytes) -> FormatoArquivo:
    """O formato só é aceito quando extensão e conteúdo concordam."""
    extensao = Path(nome_arquivo).suffix.lower()
    formato = _EXTENSOES.get(extensao)
    if formato is None:
        raise FormatoNaoSuportadoException(extensao or "sem extensão")

    if formato is FormatoArquivo.PDF:
        if not dados.startswith(b"%PDF-"):
            raise FormatoNaoSuportadoException("conteúdo não é PDF")
        return formato

    if formato is FormatoArquivo.TXT:
        if b"\x00" in dados:
            raise FormatoNaoSuportadoException("conteúdo binário em arquivo .txt")
        return formato

    if not dados.startswith(b"PK\x03\x04"):
        raise FormatoNaoSuportadoException(f"conteúdo não é {extensao[1:].upper()}")
    try:
        with zipfile.ZipFile(BytesIO(dados)) as pacote:
            nomes = pacote.namelist()
    except zipfile.BadZipFile as exc:
        raise FormatoNaoSuportadoException(
            f"arquivo {extensao[1:].upper()} ilegível"
        ) from exc
    prefixo = _PREFIXO_OOXML[formato]
    if not any(nome.startswith(prefixo) for nome in nomes):
        raise FormatoNaoSuportadoException(
            f"conteúdo não corresponde a {extensao[1:].upper()}"
        )
    return formato
