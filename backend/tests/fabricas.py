"""Arquivos de teste gerados em código — nada de binários versionados."""

from io import BytesIO

import fitz
from docx import Document
from pptx import Presentation
from pptx.util import Inches


def pdf_com_texto(paginas: list[str]) -> bytes:
    documento = fitz.open()
    for texto in paginas:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), texto, fontsize=12)
    return documento.tobytes()


def pdf_vazio(n_paginas: int = 2) -> bytes:
    documento = fitz.open()
    for _ in range(n_paginas):
        documento.new_page()
    return documento.tobytes()


def pdf_escaneado(paginas: list[str], dpi: int = 200) -> bytes:
    """Rasteriza páginas de texto em imagem: o resultado não tem camada de
    texto, exatamente como um PDF vindo de scanner."""
    origem = fitz.open("pdf", pdf_com_texto(paginas))
    destino = fitz.open()
    for pagina in origem:
        pixmap = pagina.get_pixmap(dpi=dpi)
        nova = destino.new_page(width=pagina.rect.width, height=pagina.rect.height)
        nova.insert_image(nova.rect, pixmap=pixmap)
    return destino.tobytes()


def pdf_misto(nativas: list[str], escaneadas: list[str], dpi: int = 200) -> bytes:
    """PDF com páginas de texto nativo seguidas de páginas rasterizadas — o
    caso em que um documento mistura conteúdo selecionável com scanner."""
    documento = fitz.open()
    for texto in nativas:
        documento.new_page().insert_text((72, 72), texto, fontsize=12)
    origem = fitz.open("pdf", pdf_escaneado(escaneadas, dpi=dpi))
    documento.insert_pdf(origem)
    return documento.tobytes()


def pdf_protegido(senha: str = "segredo") -> bytes:
    documento = fitz.open()
    documento.new_page().insert_text((72, 72), "conteúdo protegido", fontsize=12)
    return documento.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=senha, user_pw=senha
    )


def pdf_com_numeracao_impressa(rotulos: list[str]) -> bytes:
    """Páginas cujo texto impresso diz "Página 47" etc. — exige que a
    contagem lógica ignore isso e conte as páginas físicas."""
    documento = fitz.open()
    for rotulo in rotulos:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), f"Conteúdo da aula — {rotulo}", fontsize=12)
        pagina.insert_text((72, 700), rotulo, fontsize=10)
    return documento.tobytes()


def docx_com_secoes(secoes: list[tuple[str, list[str]]]) -> bytes:
    documento = Document()
    for titulo, paragrafos in secoes:
        documento.add_heading(titulo, level=1)
        for paragrafo in paragrafos:
            documento.add_paragraph(paragrafo)
    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def docx_com_tabela(linhas: list[list[str]]) -> bytes:
    documento = Document()
    tabela = documento.add_table(rows=len(linhas), cols=len(linhas[0]))
    for i, linha in enumerate(linhas):
        for j, valor in enumerate(linha):
            tabela.cell(i, j).text = valor
    buffer = BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def pptx_com_slides(slides: list[tuple[str, str]], notas: str | None = None) -> bytes:
    apresentacao = Presentation()
    layout = apresentacao.slide_layouts[5]  # só título
    for titulo, corpo in slides:
        slide = apresentacao.slides.add_slide(layout)
        slide.shapes.title.text = titulo
        caixa = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(2))
        caixa.text_frame.text = corpo
        if notas:
            slide.notes_slide.notes_text_frame.text = notas
    buffer = BytesIO()
    apresentacao.save(buffer)
    return buffer.getvalue()


def zip_corrompido() -> bytes:
    """Assinatura de ZIP seguida de lixo: passa pela checagem de assinatura e
    quebra na abertura."""
    return b"PK\x03\x04" + b"\x00lixo que nao e um ooxml valido" * 4


def txt_bytes(texto: str, encoding: str = "utf-8") -> bytes:
    return texto.encode(encoding)
