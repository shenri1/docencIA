import pymupdf as fitz

from backend.app.domain import OrigemTexto
from backend.app.exceptions import (
    PdfEscaneadoOcrInsuficienteException,
    PdfProtegidoException,
)
from backend.app.services.extracao.ocr import Ocr
from backend.app.services.extracao.tipos import (
    BlocoTexto,
    ClassePagina,
    ConfigExtracao,
    MetricaPagina,
    ResultadoExtracao,
    avaliar_documento,
    classificar_pagina,
)


def _verificar_protecao(documento: fitz.Document) -> None:
    if documento.needs_pass or documento.is_encrypted:
        raise PdfProtegidoException("PDF exige senha para ser aberto")
    if not documento.permissions & fitz.PDF_PERM_COPY:
        raise PdfProtegidoException("PDF sem permissão de cópia/extração de texto")


def extrair_pdf(
    dados: bytes, cfg: ConfigExtracao, ocr: Ocr | None
) -> ResultadoExtracao:
    documento = fitz.open(stream=dados, filetype="pdf")
    try:
        _verificar_protecao(documento)
        # contagem física do arquivo digital, ignorando numeração
        # impressa e rótulos de página.
        paginas_logicas = documento.page_count

        metricas: list[MetricaPagina] = []
        textos: dict[int, tuple[str, OrigemTexto]] = {}
        candidatas: list[int] = []

        for indice, pagina in enumerate(documento, start=1):
            texto = pagina.get_text("text").strip()
            tem_imagem = bool(pagina.get_images(full=True))
            metricas.append(
                MetricaPagina(
                    numero=indice, chars_nativos=len(texto), tem_imagem=tem_imagem
                )
            )
            if texto:
                textos[indice] = (texto, OrigemTexto.NATIVO)
            if len(texto) < cfg.min_chars_pagina and tem_imagem:
                candidatas.append(indice)

        if candidatas and cfg.ocr_habilitado and ocr is not None:
            # ocr_max_paginas é teto de custo síncrono, não critério de
            # legibilidade: acima dele o OCR é pulado (não processado
            # parcialmente) e quem decide é avaliar_documento, logo abaixo.
            alvo = candidatas if len(candidatas) <= cfg.ocr_max_paginas else []
            for numero in alvo:
                pagina = documento[numero - 1]
                imagem = pagina.get_pixmap(dpi=cfg.ocr_dpi).tobytes("png")
                texto_ocr, confianca = ocr.reconhecer(imagem, cfg.ocr_langs)
                anterior = metricas[numero - 1]
                metricas[numero - 1] = MetricaPagina(
                    numero=anterior.numero,
                    chars_nativos=anterior.chars_nativos,
                    tem_imagem=anterior.tem_imagem,
                    chars_ocr=len(texto_ocr.strip()),
                    confianca_ocr=confianca,
                )
                if classificar_pagina(metricas[numero - 1], cfg) is ClassePagina.OCR:
                    textos[numero] = (texto_ocr.strip(), OrigemTexto.OCR)

        veredito = avaliar_documento(metricas, cfg)
        if not veredito.legivel:
            motivo = (
                "nenhuma página com texto extraível"
                if not textos
                else "fração de páginas legíveis abaixo do limiar exigido"
            )
            if not cfg.ocr_habilitado or ocr is None:
                motivo += " (OCR indisponível nesta instalação)"
            elif len(candidatas) > cfg.ocr_max_paginas:
                motivo += (
                    f" (limite de {cfg.ocr_max_paginas} páginas por arquivo "
                    "para OCR excedido)"
                )
            raise PdfEscaneadoOcrInsuficienteException(
                veredito.paginas_ilegiveis or [m.numero for m in metricas], motivo
            )

        blocos = [
            BlocoTexto(f"página {numero}", texto, origem)
            for numero, (texto, origem) in sorted(textos.items())
        ]
        return ResultadoExtracao(blocos, paginas_logicas, veredito.origem)
    finally:
        documento.close()
