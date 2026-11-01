import zipfile
from io import BytesIO

from docx import Document
from docx.opc.exceptions import OpcError, PackageNotFoundError
from pptx import Presentation

from backend.app.core.config import settings
from backend.app.domain import OrigemTexto
from backend.app.exceptions import (
    ArquivoDescompressaoExcessivaException,
    ArquivoCorrompidoException,
    ArquivoProtegidoException,
    MaterialSemTextoException,
)
from backend.app.services.extracao.tipos import BlocoTexto, ResultadoExtracao

# Contêiner OLE: é assim que um OOXML protegido por senha se apresenta.
_ASSINATURA_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _verificar_descompressao(dados: bytes, formato: str) -> None:
    """MAX_UPLOAD_MB limita o arquivo comprimido; DEFLATE chega a 1000:1, então
    um .docx de 30 MB pode pedir GBs ao abrir. O diretório central do zip
    declara o tamanho de cada entrada sem descomprimir nada, e o zipfile do
    Python não devolve mais bytes do que esse tamanho declarado — o filtro é
    real para quem lê o pacote por ele (python-docx/python-pptx)."""
    with zipfile.ZipFile(BytesIO(dados)) as pacote:
        entradas = pacote.infolist()
    if len(entradas) > settings.max_ooxml_entradas:
        raise ArquivoDescompressaoExcessivaException(
            formato, f"pacote com mais de {settings.max_ooxml_entradas} partes"
        )
    teto = settings.max_ooxml_descomprimido_mb * 1024 * 1024
    if sum(e.file_size for e in entradas) > teto:
        raise ArquivoDescompressaoExcessivaException(
            formato,
            f"conteúdo descomprimido acima de {settings.max_ooxml_descomprimido_mb} MB",
        )


def _abrir(dados: bytes, abridor, formato: str):
    if dados.startswith(_ASSINATURA_OLE):
        raise ArquivoProtegidoException(formato)
    try:
        _verificar_descompressao(dados, formato)
        return abridor(BytesIO(dados))
    except (PackageNotFoundError, OpcError, zipfile.BadZipFile) as exc:
        raise ArquivoCorrompidoException(formato) from exc


def _textos_da_tabela(tabela) -> list[str]:
    """Textos das células, sem repetir células mescladas — python-docx devolve
    a mesma célula para cada posição ocupada pela mesclagem."""
    vistos: set[int] = set()
    textos: list[str] = []
    for linha in tabela.rows:
        for celula in linha.cells:
            identidade = id(celula._tc)
            if identidade in vistos:
                continue
            vistos.add(identidade)
            texto = celula.text.strip()
            if texto:
                textos.append(texto)
    return textos


def extrair_docx(dados: bytes) -> ResultadoExtracao:
    """DOCX não tem página fixa (depende de renderização), então a localização
    é por seção e parágrafo, e a contagem de páginas fica nula."""
    documento = _abrir(dados, Document, "docx")
    blocos: list[BlocoTexto] = []
    secao_atual = ""
    numero = 0
    for paragrafo in documento.paragraphs:
        texto = paragrafo.text.strip()
        if not texto:
            continue
        if paragrafo.style is not None and paragrafo.style.name.startswith("Heading"):
            secao_atual = texto
            continue
        numero += 1
        localizacao = (
            f"{secao_atual} · par. {numero}" if secao_atual else f"par. {numero}"
        )
        blocos.append(BlocoTexto(localizacao, texto, OrigemTexto.NATIVO))

    # Tabelas de topo não entram em document.paragraphs — percorrer também,
    # senão o texto delas é perdido silenciosamente (violaria R2). Tabelas
    # aninhadas e outras estruturas raras seguem como limitação conhecida.
    for indice, tabela in enumerate(documento.tables, start=1):
        textos = _textos_da_tabela(tabela)
        if textos:
            blocos.append(
                BlocoTexto(f"tabela {indice}", "\n".join(textos), OrigemTexto.NATIVO)
            )

    if not blocos:
        raise MaterialSemTextoException("docx")
    return ResultadoExtracao(blocos, None, OrigemTexto.NATIVO)


def extrair_pptx(dados: bytes) -> ResultadoExtracao:
    apresentacao = _abrir(dados, Presentation, "pptx")
    slides = list(apresentacao.slides)
    blocos: list[BlocoTexto] = []
    for indice, slide in enumerate(slides, start=1):
        partes = [
            forma.text_frame.text.strip()
            for forma in slide.shapes
            if forma.has_text_frame and forma.text_frame.text.strip()
        ]
        if slide.has_notes_slide:
            notas = slide.notes_slide.notes_text_frame.text.strip()
            if notas:
                partes.append(notas)
        texto = "\n".join(partes).strip()
        if texto:
            blocos.append(BlocoTexto(f"slide {indice}", texto, OrigemTexto.NATIVO))

    if not blocos:
        raise MaterialSemTextoException("pptx")
    return ResultadoExtracao(blocos, len(slides), OrigemTexto.NATIVO)
