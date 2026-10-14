"""MathML → OMML do subconjunto da Núcleo Determinístico.

Sem atributo dependente de ordem de dicionário e sem identificador aleatório: o
XML sai igual a cada chamada, e o sha256 do DOCX continua estável.
Elemento fora da tabela → `None`, e a fórmula vira texto cru.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from backend.app.services.notacao import para_mathml

_M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_NARY = {"∑", "∫", "∏"}
_SOBRE = {"msub", "msup", "msubsup", "munder", "mover", "munderover"}


class _ForaDaTabela(Exception):
    pass


def _nome(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _run(texto: str, normal: bool = False) -> str:
    estilo = '<m:rPr><m:sty m:val="p"/></m:rPr>' if normal else ""
    return f'<m:r>{estilo}<m:t xml:space="preserve">{escape(texto)}</m:t></m:r>'


def _filhos(el: ET.Element) -> str:
    return "".join(_no(f) for f in el)


def _sequencia(filhos: list[ET.Element]) -> str:
    """Um operador n-ário leva como operando tudo que vem depois dele na linha."""
    saida: list[str] = []
    for i, filho in enumerate(filhos):
        base = filho[0] if len(filho) and _nome(filho) in _SOBRE else None
        if base is not None and _nome(base) == "mo" and (base.text or "") in _NARY:
            saida.append(_nary(filho, filhos[i + 1 :]))
            break
        saida.append(_no(filho))
    return "".join(saida)


def _nary(el: ET.Element, resto: list[ET.Element]) -> str:
    nome = _nome(el)
    caractere = el[0].text or ""
    sub = sup = ""
    if nome in {"msub", "munder"}:
        sub = _no(el[1])
    elif nome in {"msup", "mover"}:
        sup = _no(el[1])
    else:
        sub, sup = _no(el[1]), _no(el[2])
    partes = f"<m:naryPr><m:chr m:val={quoteattr(caractere)}/></m:naryPr>"
    if sub:
        partes += f"<m:sub>{sub}</m:sub>"
    if sup:
        partes += f"<m:sup>{sup}</m:sup>"
    return f"<m:nary>{partes}<m:e>{_sequencia(resto)}</m:e></m:nary>"


def _delimitado(el: ET.Element) -> str | None:
    if len(el) < 3 or _nome(el[0]) != "mo" or _nome(el[-1]) != "mo":
        return None
    abre, fecha = el[0].text or "", el[-1].text or ""
    # `\left…\right` sai com fence="true"; a matriz, com o mtable no meio.
    cercado = el[0].get("fence") == "true" and el[-1].get("fence") == "true"
    matriz = (abre, fecha) in {("(", ")"), ("[", "]")} and any(
        _nome(f) == "mtable" for f in el
    )
    if not (cercado or matriz):
        return None
    corpo = _sequencia(list(el[1:-1]))
    return (
        f"<m:d><m:dPr><m:begChr m:val={quoteattr(abre)}/><m:endChr m:val={quoteattr(fecha)}/>"
        f"</m:dPr><m:e>{corpo}</m:e></m:d>"
    )


def _no(el: ET.Element) -> str:
    nome = _nome(el)
    if nome in {"mi", "mn", "mo", "mtext"}:
        return _run(
            el.text or "", normal=nome == "mtext" or el.get("mathvariant") == "normal"
        )
    if nome in {"math", "mrow"}:
        return _delimitado(el) or _sequencia(list(el))
    if nome == "msup":
        return f"<m:sSup><m:e>{_no(el[0])}</m:e><m:sup>{_no(el[1])}</m:sup></m:sSup>"
    if (
        nome in {"msub", "munder"}
        and _nome(el[0]) in {"mi", "mo"}
        and el[0].text == "lim"
    ):
        # O latex2mathml emite `\lim_{x}` como msub sobre <mo>lim</mo>.
        return (
            f"<m:limLow><m:e>{_run('lim', normal=True)}</m:e>"
            f"<m:lim>{_no(el[1])}</m:lim></m:limLow>"
        )
    if nome == "msub":
        return f"<m:sSub><m:e>{_no(el[0])}</m:e><m:sub>{_no(el[1])}</m:sub></m:sSub>"
    if nome in {"msubsup", "munderover"}:
        return (
            f"<m:sSubSup><m:e>{_no(el[0])}</m:e><m:sub>{_no(el[1])}</m:sub>"
            f"<m:sup>{_no(el[2])}</m:sup></m:sSubSup>"
        )
    if nome == "mfrac":
        return f"<m:f><m:num>{_no(el[0])}</m:num><m:den>{_no(el[1])}</m:den></m:f>"
    if nome == "msqrt":
        return (
            '<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>'
            f"<m:e>{_filhos(el)}</m:e></m:rad>"
        )
    if nome == "mroot":
        return f"<m:rad><m:deg>{_no(el[1])}</m:deg><m:e>{_no(el[0])}</m:e></m:rad>"
    if nome == "mspace":
        # `\,` do latex2mathml; espaço fino fixo, para o DOCX seguir determinístico.
        return _run("\u2009")
    if nome == "mtable":
        return f"<m:m>{_filhos(el)}</m:m>"
    if nome == "mtr":
        return f"<m:mr>{_filhos(el)}</m:mr>"
    if nome == "mtd":
        return f"<m:e>{_filhos(el)}</m:e>"
    raise _ForaDaTabela(nome)


def para_omml(mathml: ET.Element) -> str | None:
    try:
        corpo = _no(mathml)
    except _ForaDaTabela, IndexError:
        return None
    return f'<m:oMath xmlns:m="{_M}">{corpo}</m:oMath>'


def omml_da_formula(latex: str, destaque: bool) -> str | None:
    mathml = para_mathml(latex)
    omml = para_omml(mathml) if mathml is not None else None
    if omml is None:
        return None
    if destaque:
        interno = omml.removeprefix(f'<m:oMath xmlns:m="{_M}">').removesuffix(
            "</m:oMath>"
        )
        return f'<m:oMathPara xmlns:m="{_M}"><m:oMath>{interno}</m:oMath></m:oMathPara>'
    return omml
