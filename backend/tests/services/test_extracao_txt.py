import pytest

from backend.app.domain import OrigemTexto
from backend.app.exceptions import MaterialSemTextoException
from backend.app.services.extracao.txt import extrair_txt
from backend.tests.fabricas import txt_bytes


def test_txt_vira_blocos_por_linha_em_branco():
    resultado = extrair_txt(txt_bytes("primeiro bloco\nsegue\n\nsegundo bloco\n"))
    assert [b.localizacao for b in resultado.blocos] == ["linhas 1–2", "linhas 4–4"]
    assert resultado.blocos[0].texto == "primeiro bloco\nsegue"
    assert resultado.blocos[0].origem is OrigemTexto.NATIVO


def test_txt_nao_tem_contagem_de_paginas():
    assert extrair_txt(txt_bytes("conteúdo qualquer")).contagem_paginas_logicas is None


def test_txt_em_cp1252_e_decodificado():
    resultado = extrair_txt(txt_bytes("ação e coração", encoding="cp1252"))
    assert "ação" in resultado.blocos[0].texto


def test_txt_vazio_levanta_sem_texto():
    with pytest.raises(MaterialSemTextoException):
        extrair_txt(txt_bytes("   \n\n  "))


def test_txt_binario_levanta_sem_texto():
    with pytest.raises(MaterialSemTextoException):
        extrair_txt(b"\x00\x01\x02binario")
