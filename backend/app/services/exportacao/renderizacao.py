"""Renderização DOCX — Núcleo Determinístico, puro.

Recebe as estruturas que as já montam e devolve bytes. Não
abre sessão de banco, não decide conteúdo, não chama LLM.

Fidelidade: texto persistido entra sem `strip`, sem troca de aspas, sem
capitalização. Quebra de linha dentro do texto vira quebra de linha no DOCX, que
é o que o python-docx faz ao atribuir texto a um run.

Única exceção, imposta pelo formato: caractere que o XML não representa (controle
C0, surrogate solto, U+FFFE/U+FFFF) sai como símbolo visível (`_legivel`). O
validador aceita e sinaliza esse texto (o LaTeX mal escapado no JSON vira
U+000C), então ele chega aqui, e o python-docx recusaria o documento inteiro.
O que está persistido não muda.

Reprodutibilidade: medido com python-docx 1.2.0, o mesmo conteúdo renderizado
duas vezes muda SÓ a data das entradas do zip. `normalizar_zip` fixa essa data,
e o sha256 do arquivo entregue vira prova conferível com `sha256sum`. Por isso
nenhuma data entra no documento.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips

from backend.app.services.critico.auditor_service import ResumoAuditoria
from backend.app.services.exportacao.notacao_omml import omml_da_formula
from backend.app.services.geracao.formatos import LETRAS_ITEM
from backend.app.services.notacao import Texto, separar
from backend.app.services.provas.gabarito import FonteGabarito, Gabarito, ItemGabarito
from backend.app.services.provas.leitura import ItemLido, ProvaLida
from backend.app.services.provas.verificacao import Verificacao

LINHAS_RESPOSTA_DISCURSIVA = 8
# Padrão fixo, das boas práticas de formatação de provas.
FONTE = "Arial"
TAMANHO_TEXTO = Pt(12)
TAMANHO_APOIO = Pt(10)
TAMANHO_TITULO = Pt(14)
# Em twips, não em cm: Cm(21) passa por EMU e arredonda para 11905.
_A4 = (Twips(11906), Twips(16838))
_MARGENS = {
    "top": Twips(1701),
    "left": Twips(1701),
    "bottom": Twips(1134),
    "right": Twips(1134),
}
# Cabem na área útil (16 cm) em Arial 12: cada sublinhado ≈ 0,235 cm.
_LINHA = "_" * 66
_LINHA_CAMPO = "_" * 50
_ATRIBUTOS_DE_FONTE = ("ascii", "hAnsi", "eastAsia", "cs")
# Menor data que o formato zip representa.
_DATA_FIXA = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Cabecalho:
    disciplina: str
    periodo: str
    # O único dado de identificação que o sistema tem. Instituição e
    # curso são do cabeçalho institucional, que o docente insere no Word.
    professor: str
    versao_banco: str
    revisao_banco: int


def normalizar_zip(dados: bytes) -> bytes:
    """Reescreve o zip com as mesmas entradas, na mesma ordem, com data fixa. É a
    única transformação sobre os bytes do python-docx."""
    origem = zipfile.ZipFile(io.BytesIO(dados))
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for info in origem.infolist():
            nova = zipfile.ZipInfo(info.filename, date_time=_DATA_FIXA)
            nova.compress_type = zipfile.ZIP_DEFLATED
            # Fixos também: variam com o sistema operacional que gravou.
            nova.create_system = 0
            nova.external_attr = 0
            destino.writestr(nova, origem.read(info.filename))
    return saida.getvalue()


# O que o XML 1.0 não aceita: controles C0 exceto tab, LF e CR; surrogates (o
# JSON "\ud800" gera um solto); U+FFFE e U+FFFF.
_ILEGAL_NO_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


def _substituto(achado: re.Match[str]) -> str:
    codigo = ord(achado.group())
    # Controles têm símbolo próprio (U+2400 + código: ␌ para U+000C); o resto
    # fica como caractere de substituição.
    return chr(0x2400 + codigo) if codigo < 0x20 else "�"


def _legivel(texto: str) -> str:
    """Troca o que o DOCX não comporta por um símbolo visível: o docente vê
    onde o texto está corrompido em vez de a exportação inteira falhar."""
    return _ILEGAL_NO_XML.sub(_substituto, texto)


def _salvar(documento) -> bytes:
    buffer = io.BytesIO()
    documento.save(buffer)
    return normalizar_zip(buffer.getvalue())


def _fonte_explicita(estilo) -> None:
    """Arial nos quatro atributos e sem os de tema: com `w:asciiTheme` presente,
    o Word ignora `w:ascii`."""
    fontes = estilo.element.get_or_add_rPr().get_or_add_rFonts()
    for atributo in list(fontes.attrib):
        if "heme" in atributo:  # asciiTheme, hAnsiTheme, eastAsiaTheme, cstheme
            del fontes.attrib[atributo]
    for atributo in _ATRIBUTOS_DE_FONTE:
        fontes.set(qn(f"w:{atributo}"), FONTE)


def _aplicar_padrao(documento) -> None:
    secao = documento.sections[0]
    secao.page_width, secao.page_height = _A4
    secao.top_margin = _MARGENS["top"]
    secao.left_margin = _MARGENS["left"]
    secao.bottom_margin = _MARGENS["bottom"]
    secao.right_margin = _MARGENS["right"]

    normal = documento.styles["Normal"]
    _fonte_explicita(normal)
    normal.font.size = TAMANHO_TEXTO
    formato = normal.paragraph_format
    formato.space_before = Pt(0)
    formato.space_after = Pt(6)
    formato.line_spacing_rule = WD_LINE_SPACING.SINGLE

    titulo = documento.styles["Heading 1"]
    _fonte_explicita(titulo)
    titulo.font.size = TAMANHO_TITULO
    titulo.font.bold = True
    titulo.font.color.rgb = RGBColor(0, 0, 0)
    cor = titulo.element.rPr.find(qn("w:color"))
    for atributo in ("w:themeColor", "w:themeShade", "w:themeTint"):
        cor.attrib.pop(qn(atributo), None)


def separar_contexto(enunciado: str, contexto: str | None) -> tuple[str | None, str]:
    """Mesma regra de `substituicao_service._pergunta`: o enunciado montado é
    `contexto + "\\n\\n" + pergunta`. Sem esse prefixo exato, nada é
    separado e o enunciado sai inteiro."""
    if contexto and contexto.strip() and enunciado.startswith(f"{contexto}\n\n"):
        return contexto, enunciado[len(contexto) + 2 :]
    return None, enunciado


def _paragrafo(documento, *partes: str, tamanho=None):
    """Um parágrafo com um run por parte: o texto persistido fica num run só,
    sem concatenação que o transforme."""
    paragrafo = documento.add_paragraph()
    for parte in partes:
        run = paragrafo.add_run(_legivel(parte))
        if tamanho is not None:
            run.font.size = tamanho
    return paragrafo


def _paragrafo_modelo(
    documento, rotulo: str, texto: str, *, tamanho=None, alinhamento=None, recuo=None
) -> list:
    """Como `_paragrafo`, mas o texto escrito pelo modelo pode ter fórmula
O texto persistido não é reescrito: fórmula que não converte sai
    crua, com o delimitador. O rótulo ("3. ", "A) ") é texto do sistema e não
    recebe `tamanho`. Fórmula em destaque abre parágrafos extras: a formatação
    vale para todos. A fórmula OMML sai no tamanho do `Normal` (limite
    conhecido)."""
    paragrafo = documento.add_paragraph()
    criados = [paragrafo]

    def _novo() -> None:
        nonlocal paragrafo
        paragrafo = documento.add_paragraph()
        criados.append(paragrafo)

    def _texto(conteudo: str) -> None:
        run = paragrafo.add_run(_legivel(conteudo))
        if tamanho is not None:
            run.font.size = tamanho

    if rotulo:
        paragrafo.add_run(_legivel(rotulo))
    segmentos = separar(texto)
    if not segmentos:
        _texto(texto)
    for segmento in segmentos:
        if isinstance(segmento, Texto):
            _texto(segmento.conteudo)
            continue
        # Com caractere ilegal o conversor o trata como espaço e devolve outra
        # equação ("\x0crac{a}{b}" viraria "r a c a b"): sai crua, como a que
        # não converte, e o símbolo mostra onde está o defeito.
        omml = (
            None
            if _ILEGAL_NO_XML.search(segmento.latex)
            else omml_da_formula(segmento.latex, segmento.destaque)
        )
        if omml is None:
            _texto(
                f"\\[{segmento.latex}\\]"
                if segmento.destaque
                else f"\\({segmento.latex}\\)"
            )
        elif segmento.destaque:
            # Em destaque: parágrafo próprio, e o texto seguinte abre outro.
            if len(paragrafo._p) > (1 if paragrafo._p.pPr is not None else 0):
                _novo()
            paragrafo._p.append(parse_xml(omml))
            _novo()
        else:
            paragrafo._p.append(parse_xml(omml))
    for p in criados:
        if alinhamento is not None:
            p.alignment = alinhamento
        if recuo is not None:
            p.paragraph_format.left_indent = recuo
    return criados


def _quebra_de_pagina(documento) -> None:
    documento.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


_RECUO_ALTERNATIVA = Twips(283)  # 0,5 cm


def _item_da_prova(documento, item: ItemLido) -> None:
    justificado = WD_ALIGN_PARAGRAPH.JUSTIFY
    contexto, resto = separar_contexto(item.enunciado, item.contexto)
    if contexto is None:
        _paragrafo_modelo(
            documento, f"{item.posicao}. ", item.enunciado, alinhamento=justificado
        )
    else:
        # O contexto é o texto de apoio: 10 pt. O "\n\n" que o separa
        # vira a quebra entre os dois parágrafos; o texto não muda.
        _paragrafo_modelo(
            documento,
            f"{item.posicao}. ",
            contexto,
            tamanho=TAMANHO_APOIO,
            alinhamento=justificado,
        )
        _paragrafo_modelo(documento, "", resto, alinhamento=justificado)
    if item.alternativas:
        for alternativa in item.alternativas:
            _paragrafo_modelo(
                documento,
                f"{alternativa.letra}) ",
                alternativa.texto,
                recuo=_RECUO_ALTERNATIVA,
            )
    else:
        for _ in range(LINHAS_RESPOSTA_DISCURSIVA):
            _paragrafo(documento, _LINHA)


def renderizar_conteudo_puro(
    cabecalho: Cabecalho, prova_a: ProvaLida, prova_b: ProvaLida
) -> bytes:
    """Provas A e B, sem gabarito e sem fontes internas. Não tem como vazar: a
    `ProvaLida` não tem campo para nada disso."""
    documento = docx.Document()
    _aplicar_padrao(documento)
    for indice, prova in enumerate((prova_a, prova_b)):
        if indice:
            _quebra_de_pagina(documento)
        documento.add_heading(
            _legivel(
                f"{cabecalho.disciplina} — {cabecalho.periodo} — Prova {prova.versao}"
            ),
            level=1,
        )
        _paragrafo(documento, "Professor: ", cabecalho.professor)
        _paragrafo(documento, "Aluno: ", _LINHA_CAMPO)
        _paragrafo(documento, "Matrícula: ", "_" * 20)
        _paragrafo(documento, "Data: ", "____/____/________")
        _paragrafo(documento, "Nota: ", "_" * 10)
        for item in prova.itens:
            _item_da_prova(documento, item)
    return _salvar(documento)


# Texto do sistema, não do aprovado: o texto persistido sai intacto, e
# o aviso é como o docente fica sabendo que um comentário pode apontar a
# alternativa errada numa prova permutada.
AVISO_CITA_LETRA = (
    "Aviso: o comentário cita letra de alternativa; a letra pode não "
    "corresponder à desta prova."
)
AVISO_SEM_LETRA = (
    "Aviso: os motivos das alternativas erradas não indicam a qual alternativa "
    "se referem."
)
# Escrito, nunca omitido: seção ausente seria indistinguível de "auditado e sem
# achados".
NAO_AUDITADO = "Não auditado nesta revisão."


def _fonte_texto(fonte: FonteGabarito) -> str:
    return f"{fonte.identificador_material}, {fonte.localizacao}"


def _item_do_gabarito(documento, item: ItemGabarito) -> None:
    _paragrafo(documento, f"{item.posicao}. Questão {item.numero} do banco")
    if item.cita_letra:
        _paragrafo(documento, AVISO_CITA_LETRA)
    if item.invalidacoes_sem_letra:
        _paragrafo(documento, AVISO_SEM_LETRA)

    if item.letra is not None:
        _paragrafo(documento, "Resposta: ", item.letra)
    if item.justificativa_correta is not None:
        _paragrafo_modelo(documento, "Justificativa: ", item.justificativa_correta)
    for invalidacao in item.invalidacoes:
        rotulo = f"{invalidacao.letra}) " if invalidacao.letra else "— "
        _paragrafo_modelo(documento, rotulo, invalidacao.motivo)
    item_atual = None
    for aspecto in item.aspectos:
        if aspecto.item is not None and aspecto.item != item_atual:
            item_atual = aspecto.item
            _paragrafo(documento, f"Item {LETRAS_ITEM[aspecto.item - 1]})")
        _paragrafo_modelo(documento, f"{aspecto.ordem}. ", aspecto.texto)
        _paragrafo(documento, "Fonte: ", _fonte_texto(aspecto.fonte))
        if aspecto.fonte.trecho_base is not None:
            _paragrafo(
                documento,
                "Trecho-base: ",
                aspecto.fonte.trecho_base,
                tamanho=TAMANHO_APOIO,
            )
    if item.objetivo_cognitivo is not None:
        _paragrafo_modelo(documento, "Objetivo cognitivo: ", item.objetivo_cognitivo)
    for fonte in item.fontes:
        _paragrafo(documento, "Fonte: ", _fonte_texto(fonte))
        if fonte.trecho_base is not None:
            _paragrafo(
                documento, "Trecho-base: ", fonte.trecho_base, tamanho=TAMANHO_APOIO
            )


def _verificacao(documento, verificacao: Verificacao) -> None:
    documento.add_heading("Verificação pós-montagem", level=1)
    _paragrafo(
        documento,
        f"Colisões de letra entre A e B: {verificacao.colisoes_letras} de "
        f"{verificacao.posicoes_objetivas}",
    )
    _paragrafo(documento, f"Questões compartilhadas: {verificacao.compartilhadas}")
    for subtema, quantas in sorted(verificacao.subtemas_compartilhados.items()):
        _paragrafo(documento, f"Subtema compartilhado: {subtema} ({quantas})")
    # Sempre "nenhuma": violação teria bloqueado a exportação antes daqui.
    violacoes = "; ".join(verificacao.violacoes) or "nenhuma"
    _paragrafo(documento, f"Violações: {violacoes}")


def _auditoria(documento, auditoria: ResumoAuditoria) -> None:
    documento.add_heading("Auditoria sob comando", level=1)
    if auditoria.auditadas == 0:
        _paragrafo(documento, NAO_AUDITADO)
        return
    _paragrafo(
        documento,
        f"Revisão auditada: {auditoria.revisao_auditada}; questões auditadas: "
        f"{auditoria.auditadas}; com achado: {auditoria.proporcao_com_achado}%",
    )
    if auditoria.sem_verificacao_de_forma:
        _paragrafo(
            documento,
            "Assimetria de forma: não se aplica a "
            f"{auditoria.sem_verificacao_de_forma} questão(ões) de afirmativas ou "
            "asserção-razão, cujas alternativas o sistema monta.",
        )
    for questao in auditoria.questoes:
        _paragrafo(documento, f"Questão {questao.numero}")
        for achado in questao.achados:
            _paragrafo(documento, f"{achado.risco.value} — alternativa {achado.alvo}")
            if achado.localizacao is not None:
                _paragrafo(documento, "Localização: ", achado.localizacao)
            if achado.trecho_fonte is not None:
                _paragrafo(
                    documento,
                    "Trecho: ",
                    achado.trecho_fonte,
                    tamanho=TAMANHO_APOIO,
                )
            _paragrafo(documento, "Proposta de ajuste: ", achado.proposta_ajuste)


def renderizar_metadados(
    cabecalho: Cabecalho,
    gabarito_a: Gabarito,
    gabarito_b: Gabarito,
    verificacao: Verificacao,
    auditoria: ResumoAuditoria,
) -> bytes:
    """Gabaritos comentados (que já trazem as fontes internas), verificação
    pós-montagem e auditori. Este arquivo NÃO vai para o aluno."""
    documento = docx.Document()
    _aplicar_padrao(documento)
    documento.add_heading(
        _legivel(f"{cabecalho.disciplina} — {cabecalho.periodo} — Metadados"), level=1
    )
    _paragrafo(
        documento,
        f"Banco {cabecalho.versao_banco}, revisão {cabecalho.revisao_banco}",
    )
    for gabarito in (gabarito_a, gabarito_b):
        documento.add_heading(f"Gabarito comentado — Prova {gabarito.versao}", level=1)
        for item in gabarito.itens:
            _item_do_gabarito(documento, item)
    _verificacao(documento, verificacao)
    _auditoria(documento, auditoria)
    return _salvar(documento)
