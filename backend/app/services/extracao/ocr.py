import shutil
from io import BytesIO
from typing import Protocol

import pytesseract
from PIL import Image

from backend.app.core.config import settings


class Ocr(Protocol):
    def reconhecer(self, imagem_png: bytes, langs: str) -> tuple[str, float]:
        """Devolve (texto, confiança média 0–100)."""
        ...


def ocr_disponivel() -> bool:
    caminho = settings.tesseract_cmd or "tesseract"
    return shutil.which(caminho) is not None


class OcrTesseract:
    def __init__(self) -> None:
        if settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    def reconhecer(self, imagem_png: bytes, langs: str) -> tuple[str, float]:
        imagem = Image.open(BytesIO(imagem_png))
        dados = pytesseract.image_to_data(
            imagem, lang=langs, output_type=pytesseract.Output.DICT
        )
        palavras = [
            (texto, float(conf))
            for texto, conf in zip(dados["text"], dados["conf"], strict=False)
            if texto.strip() and float(conf) > 0
        ]
        if not palavras:
            return "", 0.0
        texto = " ".join(palavra for palavra, _ in palavras)
        confianca = sum(conf for _, conf in palavras) / len(palavras)
        return texto, confianca
