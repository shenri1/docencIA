# ruff: noqa: ISC004 — XMLs de referência: concatenação implícita é a forma legível.
import xml.etree.ElementTree as ET

import pytest

from backend.app.services.exportacao.notacao_omml import omml_da_formula, para_omml

NS = "http://www.w3.org/1998/Math/MathML"


def _mml(corpo: str) -> ET.Element:
    return ET.fromstring(f'<math xmlns="{NS}">{corpo}</math>')


def _limpo(omml: str) -> str:
    return omml.split(">", 1)[1].rsplit("</m:oMath>", 1)[0]


REFERENCIAS = {
    "espaco": (
        '<mspace width="0.167em"/>',
        '<m:r><m:t xml:space="preserve">\u2009</m:t></m:r>',
    ),
    "parenteses": (
        '<mrow><mo fence="true" form="prefix">(</mo><mi>a</mi>'
        '<mo fence="true" form="postfix">)</mo></mrow>',
        '<m:d><m:dPr><m:begChr m:val="("/><m:endChr m:val=")"/></m:dPr>'
        '<m:e><m:r><m:t xml:space="preserve">a</m:t></m:r></m:e></m:d>',
    ),
    "run": ("<mi>x</mi>", '<m:r><m:t xml:space="preserve">x</m:t></m:r>'),
    "sup": (
        "<msup><mi>x</mi><mn>2</mn></msup>",
        '<m:sSup><m:e><m:r><m:t xml:space="preserve">x</m:t></m:r></m:e>'
        '<m:sup><m:r><m:t xml:space="preserve">2</m:t></m:r></m:sup></m:sSup>',
    ),
    "sub": (
        "<msub><mi>x</mi><mn>1</mn></msub>",
        '<m:sSub><m:e><m:r><m:t xml:space="preserve">x</m:t></m:r></m:e>'
        '<m:sub><m:r><m:t xml:space="preserve">1</m:t></m:r></m:sub></m:sSub>',
    ),
    "frac": (
        "<mfrac><mi>a</mi><mi>b</mi></mfrac>",
        '<m:f><m:num><m:r><m:t xml:space="preserve">a</m:t></m:r></m:num>'
        '<m:den><m:r><m:t xml:space="preserve">b</m:t></m:r></m:den></m:f>',
    ),
    "sqrt": (
        "<msqrt><mi>x</mi></msqrt>",
        '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>'
        '<m:e><m:r><m:t xml:space="preserve">x</m:t></m:r></m:e></m:rad>',
    ),
    "root": (
        "<mroot><mi>x</mi><mn>3</mn></mroot>",
        '<m:rad><m:deg><m:r><m:t xml:space="preserve">3</m:t></m:r></m:deg>'
        '<m:e><m:r><m:t xml:space="preserve">x</m:t></m:r></m:e></m:rad>',
    ),
    "nary": (
        "<mrow><munderover><mo>∑</mo><mi>i</mi><mi>n</mi></munderover><mi>i</mi></mrow>",
        '<m:nary><m:naryPr><m:chr m:val="∑"/></m:naryPr>'
        '<m:sub><m:r><m:t xml:space="preserve">i</m:t></m:r></m:sub>'
        '<m:sup><m:r><m:t xml:space="preserve">n</m:t></m:r></m:sup>'
        '<m:e><m:r><m:t xml:space="preserve">i</m:t></m:r></m:e></m:nary>',
    ),
    "limite": (
        "<msub><mo>lim</mo><mi>x</mi></msub>",
        '<m:limLow><m:e><m:r><m:rPr><m:sty m:val="p"/></m:rPr>'
        '<m:t xml:space="preserve">lim</m:t></m:r></m:e>'
        '<m:lim><m:r><m:t xml:space="preserve">x</m:t></m:r></m:lim></m:limLow>',
    ),
    "matriz": (
        "<mrow><mo>(</mo><mtable><mtr><mtd><mn>1</mn></mtd><mtd><mn>0</mn></mtd></mtr></mtable><mo>)</mo></mrow>",
        '<m:d><m:dPr><m:begChr m:val="("/><m:endChr m:val=")"/></m:dPr>'
        '<m:e><m:m><m:mr><m:e><m:r><m:t xml:space="preserve">1</m:t></m:r></m:e>'
        '<m:e><m:r><m:t xml:space="preserve">0</m:t></m:r></m:e></m:mr></m:m></m:e></m:d>',
    ),
}


@pytest.mark.parametrize("nome", REFERENCIAS)
def test_mapeamento_de_referencia(nome):
    entrada, esperado = REFERENCIAS[nome]
    assert _limpo(para_omml(_mml(entrada))) == esperado


def test_elemento_desconhecido_devolve_none():
    assert para_omml(_mml("<mi>x</mi><menclose><mi>y</mi></menclose>")) is None


def test_caractere_especial_do_xml_sai_escapado():
    assert "&lt;" in para_omml(_mml("<mo>&lt;</mo>"))


def test_destaque_vira_omathpara():
    assert omml_da_formula("x^2", destaque=True).startswith("<m:oMathPara")
    assert omml_da_formula("x^2", destaque=False).startswith("<m:oMath ")


def test_formula_fora_do_conversor_devolve_none():
    assert omml_da_formula(r"\frac{a}", destaque=False) is None


def test_saida_e_deterministica():
    assert omml_da_formula(r"\frac{a}{b}", False) == omml_da_formula(
        r"\frac{a}{b}", False
    )


@pytest.mark.parametrize(
    ("latex", "marca"),
    [
        (r"\frac{a}{b}", "<m:f>"),
        (r"x^2", "<m:sSup>"),
        (r"\sqrt{x}", "<m:rad>"),
        (r"\sum_{i=1}^{n} i", "<m:nary>"),
        (r"\int_0^1 x", "<m:nary>"),
    ],
)
def test_latex_ate_omml(latex, marca):
    omml = omml_da_formula(latex, destaque=False)
    assert omml is not None and marca in omml
