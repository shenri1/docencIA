import dataclasses
import hashlib
import io
import time
import zipfile

import docx

from backend.app.domain import EstadoProva, FaixaDificuldade, TipoQuestao
from backend.app.services.exportacao.renderizacao import (
    LINHAS_RESPOSTA_DISCURSIVA,
    Cabecalho,
    normalizar_zip,
    renderizar_conteudo_puro,
)
from backend.app.services.provas.leitura import AlternativaLida, ItemLido, ProvaLida

CABECALHO = Cabecalho(
    disciplina="Algoritmos",
    periodo="2026.2",
    professor="Ana Souza",
    versao_banco="v1",
    revisao_banco=3,
)


def paragrafos(dados: bytes) -> list[str]:
    """Lê de volta com o próprio python-docx: é assim que se confere fidelidade."""
    return [p.text for p in docx.Document(io.BytesIO(dados)).paragraphs]


def prova(versao: str, itens: list[ItemLido]) -> ProvaLida:
    return ProvaLida(
        prova_id=1 if versao == "A" else 2,
        versao=versao,
        estado=EstadoProva.MONTADA,
        n_questoes=len(itens),
        n_objetivas=sum(1 for i in itens if i.alternativas),
        n_discursivas=sum(1 for i in itens if not i.alternativas),
        revisao_banco=3,
        banco_revisao_atual=3,
        desatualizada=False,
        itens=itens,
    )


def objetiva(
    posicao: int, enunciado: str, textos: list[str], contexto: str | None = None
) -> ItemLido:
    return ItemLido(
        posicao=posicao,
        numero=posicao,
        tipo=TipoQuestao.OBJETIVA,
        faixa_dificuldade=FaixaDificuldade.MEDIA,
        enunciado=enunciado,
        alternativas=[
            AlternativaLida(letra, texto) for letra, texto in zip("ABCDE", textos)
        ],
        contexto=contexto,
    )


def discursiva(posicao: int, enunciado: str) -> ItemLido:
    return ItemLido(
        posicao=posicao,
        numero=posicao,
        tipo=TipoQuestao.DISCURSIVA,
        faixa_dificuldade=FaixaDificuldade.MEDIA,
        enunciado=enunciado,
        alternativas=[],
    )


# --- normalizar_zip ---


def _docx_cru(texto: str) -> bytes:
    documento = docx.Document()
    documento.add_paragraph(texto)
    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def test_mesmo_conteudo_normalizado_da_bytes_identicos():
    """Medido: sem normalizar, só a data das entradas do zip muda. O zip
    guarda hora com resolução de 2 s, por isso o intervalo."""
    a = _docx_cru("Qual estrutura a BFS usa?")
    time.sleep(2.1)
    b = _docx_cru("Qual estrutura a BFS usa?")
    assert a != b
    assert normalizar_zip(a) == normalizar_zip(b)


def test_normalizar_nao_muda_o_conteudo_das_entradas():
    original = _docx_cru("texto")
    normalizado = normalizar_zip(original)
    antes = zipfile.ZipFile(io.BytesIO(original))
    depois = zipfile.ZipFile(io.BytesIO(normalizado))
    assert antes.namelist() == depois.namelist()
    for nome in antes.namelist():
        assert antes.read(nome) == depois.read(nome)


def test_normalizar_e_idempotente():
    uma = normalizar_zip(_docx_cru("x"))
    assert normalizar_zip(uma) == uma


# --- Conteúdo Puro ---


def test_conteudo_puro_traz_as_duas_provas_na_ordem():
    a = prova(
        "A",
        [
            objetiva(
                1,
                "Qual estrutura a BFS usa?",
                ["fila", "pilha", "vetor", "grafo", "árvore"],
            )
        ],
    )
    b = prova(
        "B",
        [
            objetiva(
                1,
                "Qual estrutura a DFS usa?",
                ["pilha", "fila", "vetor", "grafo", "árvore"],
            )
        ],
    )
    textos = paragrafos(renderizar_conteudo_puro(CABECALHO, a, b))

    juntos = "\n".join(textos)
    assert juntos.index("Prova A") < juntos.index("Qual estrutura a BFS usa?")
    assert juntos.index("Qual estrutura a BFS usa?") < juntos.index("Prova B")
    assert "A) fila" in textos
    assert "B) pilha" in textos


def test_texto_persistido_sai_identico():
    """Fidelidade: sem strip, sem troca de aspas, com quebra de linha."""
    enunciado = '  Considere o grafo "G":\nqual percurso usa fila?  '
    a = prova(
        "A", [objetiva(1, enunciado, ["fila", "pilha", "vetor", "grafo", "árvore"])]
    )
    b = prova(
        "B", [objetiva(1, "outra", ["fila", "pilha", "vetor", "grafo", "árvore"])]
    )
    textos = paragrafos(renderizar_conteudo_puro(CABECALHO, a, b))
    assert any(enunciado in t for t in textos)


def test_discursiva_tem_linhas_de_resposta():
    a = prova("A", [discursiva(1, "Explique por que a BFS usa fila.")])
    b = prova("B", [discursiva(1, "Explique por que a DFS usa pilha.")])
    textos = paragrafos(renderizar_conteudo_puro(CABECALHO, a, b))
    i = textos.index("1. Explique por que a BFS usa fila.")
    linhas = textos[i + 1 : i + 1 + LINHAS_RESPOSTA_DISCURSIVA]
    assert all(set(linha) == {"_"} for linha in linhas)


def test_conteudo_puro_nao_tem_data_e_e_reproduzivel():
    a = prova("A", [objetiva(1, "x", ["a", "b", "c", "d", "e"])])
    b = prova("B", [objetiva(1, "y", ["a", "b", "c", "d", "e"])])
    uma = renderizar_conteudo_puro(CABECALHO, a, b)
    time.sleep(2.1)
    outra = renderizar_conteudo_puro(CABECALHO, a, b)
    assert hashlib.sha256(uma).digest() == hashlib.sha256(outra).digest()


def test_conteudo_puro_nao_tem_como_revelar_a_correta():
    """Por construção: ProvaLida não tem campo de correta, fonte, justificativa.
    O teste confere o documento, não só o tipo."""
    a = prova("A", [objetiva(1, "x", ["a", "b", "c", "d", "e"])])
    b = prova("B", [objetiva(1, "y", ["a", "b", "c", "d", "e"])])
    juntos = "\n".join(paragrafos(renderizar_conteudo_puro(CABECALHO, a, b)))
    for proibido in ("Gabarito", "correta", "Fonte", "P1", "Justificativa"):
        assert proibido not in juntos


from decimal import Decimal

from backend.app.domain import RiscoAuditoria, TipoGabarito
from backend.app.services.critico.auditor_service import (
    Achado,
    QuestaoAuditada,
    ResumoAuditoria,
)
from backend.app.services.exportacao.renderizacao import (
    AVISO_CITA_LETRA,
    AVISO_SEM_LETRA,
    NAO_AUDITADO,
    renderizar_metadados,
)
from backend.app.services.provas.gabarito import (
    AspectoGabarito,
    FonteGabarito,
    Gabarito,
    InvalidacaoGabarito,
    ItemGabarito,
)
from backend.app.services.provas.verificacao import Verificacao

FONTE = FonteGabarito("P1", "página 12", "A busca em largura usa uma fila.")
VERIFICACAO = Verificacao([], 1, 10, 2, {"Busca em largura": 1})


def item_objetivo(**extras) -> ItemGabarito:
    dados = dict(  # noqa: C408
        posicao=1,
        numero=7,
        tipo=TipoQuestao.OBJETIVA,
        letra="D",
        fontes=[FONTE],
        aspectos=[],
        justificativa_correta="o trecho afirma o uso de fila",
        invalidacoes=[
            InvalidacaoGabarito("A", "pilha é da DFS"),
            InvalidacaoGabarito("B", "vetor não organiza visita"),
        ],
        objetivo_cognitivo="identificar a estrutura",
        invalidacoes_sem_letra=False,
        cita_letra=False,
    )
    dados.update(extras)
    return ItemGabarito(**dados)


def gabarito(versao: str, itens: list[ItemGabarito]) -> Gabarito:
    return Gabarito(
        prova_id=1,
        versao=versao,
        modalidade=TipoGabarito.COMENTADO,
        revisao_banco=3,
        desatualizada=False,
        completo=True,
        problemas=[],
        itens=itens,
    )


def auditoria(questoes=(), auditadas=0) -> ResumoAuditoria:
    return ResumoAuditoria(
        banco_id=1,
        revisao_auditada=3,
        auditadas=auditadas,
        ja_auditadas=auditadas,
        discursivas_ignoradas=0,
        questoes=list(questoes),
        proporcao_com_achado=Decimal("0.00"),
    )


def metadados(itens_a, itens_b=None, auditoria_=None) -> list[str]:
    return paragrafos(
        renderizar_metadados(
            CABECALHO,
            gabarito("A", itens_a),
            gabarito("B", itens_b or [item_objetivo()]),
            VERIFICACAO,
            auditoria_ or auditoria(),
        )
    )


def test_metadados_traz_letra_justificativa_motivos_e_fonte():
    juntos = "\n".join(metadados([item_objetivo()]))
    assert "Resposta: D" in juntos
    assert "o trecho afirma o uso de fila" in juntos
    assert "A) pilha é da DFS" in juntos
    assert "B) vetor não organiza visita" in juntos
    assert "P1, página 12" in juntos
    assert "A busca em largura usa uma fila." in juntos


def test_invalidacao_sem_letra_sai_sem_letra_e_com_aviso():
    item = item_objetivo(
        invalidacoes=[InvalidacaoGabarito(None, "motivo solto")],
        invalidacoes_sem_letra=True,
    )
    textos = metadados([item])
    assert AVISO_SEM_LETRA in textos
    assert any(t.endswith("motivo solto") for t in textos)


def test_cita_letra_sai_com_aviso_e_texto_intacto():
    item = item_objetivo(
        justificativa_correta="A alternativa B confunde.", cita_letra=True
    )
    textos = metadados([item])
    assert AVISO_CITA_LETRA in textos
    assert any("A alternativa B confunde." in t for t in textos)


def test_item_sem_aviso_nao_ganha_aviso():
    textos = metadados([item_objetivo()])
    assert AVISO_CITA_LETRA not in textos
    assert AVISO_SEM_LETRA not in textos


def test_discursiva_traz_aspectos_com_fonte():
    item = ItemGabarito(
        posicao=2,
        numero=9,
        tipo=TipoQuestao.DISCURSIVA,
        letra=None,
        fontes=[FONTE],
        aspectos=[AspectoGabarito(1, "a fila preserva a ordem", FONTE)],
        justificativa_correta=None,
        invalidacoes=[],
        objetivo_cognitivo="explicar a estrutura",
        invalidacoes_sem_letra=False,
        cita_letra=False,
    )
    juntos = "\n".join(metadados([item]))
    assert "1. a fila preserva a ordem" in juntos
    assert "explicar a estrutura" in juntos


def test_verificacao_entra_com_os_numeros():
    juntos = "\n".join(metadados([item_objetivo()]))
    assert "Colisões de letra entre A e B: 1 de 10" in juntos
    assert "Questões compartilhadas: 2" in juntos
    assert "Violações: nenhuma" in juntos


def test_sem_auditoria_diz_nao_auditado():
    """Omitir a seção seria indistinguível de "auditado e sem achados"."""
    assert NAO_AUDITADO in metadados([item_objetivo()])


def test_auditoria_com_achado():
    achado = Achado(
        risco=RiscoAuditoria.CORRETA_NAO_UNICA,
        alvo="C",
        localizacao="página 7",
        trecho_fonte="o material também sustenta C",
        proposta_ajuste="Reescreva C.",
    )
    textos = metadados(
        [item_objetivo()],
        auditoria_=auditoria([QuestaoAuditada(7, [achado])], auditadas=10),
    )
    juntos = "\n".join(textos)
    assert NAO_AUDITADO not in textos
    assert "Questão 7" in juntos
    assert "correta_nao_unica" in juntos
    assert "o material também sustenta C" in juntos
    assert "Reescreva C." in juntos


def test_metadados_e_reproduzivel():
    uma = renderizar_metadados(
        CABECALHO,
        gabarito("A", [item_objetivo()]),
        gabarito("B", [item_objetivo()]),
        VERIFICACAO,
        auditoria(),
    )
    time.sleep(2.1)
    outra = renderizar_metadados(
        CABECALHO,
        gabarito("A", [item_objetivo()]),
        gabarito("B", [item_objetivo()]),
        VERIFICACAO,
        auditoria(),
    )
    assert uma == outra


def test_gabarito_com_itens_agrupa_os_aspectos_por_item():
    item = item_objetivo(
        posicao=2,
        numero=9,
        tipo=TipoQuestao.DISCURSIVA,
        letra=None,
        aspectos=[
            AspectoGabarito(1, "camadas", FONTE, item=1),
            AspectoGabarito(2, "pesos", FONTE, item=2),
        ],
        justificativa_correta=None,
        invalidacoes=[],
    )
    textos = metadados([item])
    assert (
        textos.index("Item a)")
        < textos.index("1. camadas")
        < textos.index("Item b)")
        < textos.index("2. pesos")
    )


def test_discursiva_sem_itens_nao_ganha_titulo_de_item():
    item = item_objetivo(
        tipo=TipoQuestao.DISCURSIVA,
        letra=None,
        aspectos=[AspectoGabarito(1, "camadas", FONTE)],
        justificativa_correta=None,
        invalidacoes=[],
    )
    assert "Item a)" not in metadados([item])


def test_afirmativas_saem_em_linhas_separadas_no_conteudo_puro():
    """O python-docx converte `\\n` do run em quebra de linha: as afirmativas I–III
    saem uma por linha sem mudar o renderizador."""
    enunciado = "Avalie as afirmações a seguir.\n\nI. Primeira.\nII. Segunda."
    alternativas = [
        "I, apenas.",
        "II, apenas.",
        "I e II.",
        "I, II e III.",
        "III, apenas.",
    ]
    textos = paragrafos(
        renderizar_conteudo_puro(
            CABECALHO,
            prova("A", [objetiva(1, enunciado, alternativas)]),
            prova("B", [objetiva(1, enunciado, alternativas)]),
        )
    )
    assert any("I. Primeira.\nII. Segunda." in t for t in textos)


def test_auditoria_diz_quantas_nao_tem_verificacao_de_forma():
    resumo = dataclasses.replace(auditoria(auditadas=3), sem_verificacao_de_forma=2)
    juntos = "\n".join(metadados([item_objetivo()], auditoria_=resumo))
    assert "não se aplica a 2 questão(ões)" in juntos


# --- fórmulas ---

M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _documento_xml(dados: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        return z.read("word/document.xml").decode("utf-8")


def _prova_com(*enunciados: str) -> bytes:
    itens = [
        objetiva(i, texto, ["a", "b", "c", "d", "e"])
        for i, texto in enumerate(enunciados, 1)
    ]
    return renderizar_conteudo_puro(CABECALHO, prova("A", itens), prova("B", itens))


def test_formula_em_linha_vira_equacao_nativa():
    dados = _prova_com(r"Seja \(\frac{a}{b}\) o valor.")
    xml = _documento_xml(dados)
    assert "<m:f>" in xml
    assert "\\(" not in xml
    assert "1. Seja  o valor." in paragrafos(dados)


def test_formula_em_destaque_tem_paragrafo_proprio():
    dados = _prova_com("Antes.\n\\[x^2\\]\nDepois.")
    corpo = docx.Document(io.BytesIO(dados)).element.body
    com_equacao = [
        p for p in corpo.iter(f"{W}p") if p.find(f"{M}oMathPara") is not None
    ]
    assert len(com_equacao) == 2  # prova A e prova B
    assert all(p.find(f"{W}r") is None for p in com_equacao)
    textos = paragrafos(dados)
    assert "1. Antes.\n" in textos
    assert "\nDepois." in textos


def test_formula_que_o_conversor_recusa_sai_crua():
    xml = _documento_xml(_prova_com(r"Veja \(x^\) aqui."))
    assert r"\(x^\)" in xml
    assert "<m:oMath" not in xml


def test_formula_fora_da_tabela_sai_crua():
    # O latex2mathml aceita `\frac{a}`, mas o mapeamento não tem como montar m:f.
    xml = _documento_xml(_prova_com(r"Veja \(\frac{a}\) aqui."))
    assert r"\(\frac{a}\)" in xml
    assert "<m:oMath" not in xml


def test_delimitador_sem_par_nao_engole_o_resto():
    dados = _prova_com(r"Abre \(x^2 e segue o texto.")
    assert r"1. Abre \(x^2 e segue o texto." in "".join(paragrafos(dados))


def test_docx_com_formula_e_reproduzivel():
    um = _prova_com(r"Seja \(\frac{a}{b}\) e \[\sum_{i=1}^{n} i\].")
    dois = _prova_com(r"Seja \(\frac{a}{b}\) e \[\sum_{i=1}^{n} i\].")
    assert hashlib.sha256(um).hexdigest() == hashlib.sha256(dois).hexdigest()


def test_gabarito_interpreta_justificativa_mas_nao_o_trecho_base():
    fonte = FonteGabarito("P1", "página 12", r"A fórmula \(x\) do material.")
    item = item_objetivo(
        fontes=[fonte],
        justificativa_correta=r"Porque \(\frac{1}{2}\) vale.",
        invalidacoes=[InvalidacaoGabarito("A", r"Erra em \(x^2\).")],
    )
    xml = _documento_xml(
        renderizar_metadados(
            CABECALHO,
            gabarito("A", [item]),
            gabarito("B", [item_objetivo()]),
            VERIFICACAO,
            auditoria(),
        )
    )
    assert "<m:f>" in xml and "<m:sSup>" in xml
    assert r"A fórmula \(x\) do material." in xml


# --- formatação da prova ---

import re

import pytest
from docx.oxml.ns import qn
from docx.shared import Pt


def _parte(dados: bytes, nome: str) -> str:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        return z.read(nome).decode("utf-8")


def _os_dois_docx():
    a = prova("A", [objetiva(1, "x", ["a", "b", "c", "d", "e"])])
    b = prova("B", [objetiva(1, "y", ["a", "b", "c", "d", "e"])])
    return (
        renderizar_conteudo_puro(CABECALHO, a, b),
        renderizar_metadados(
            CABECALHO,
            gabarito("A", [item_objetivo()]),
            gabarito("B", [item_objetivo()]),
            VERIFICACAO,
            auditoria(),
        ),
    )


@pytest.mark.parametrize("indice", [0, 1])
def test_pagina_a4_com_margens_3_e_2(indice):
    xml = _documento_xml(_os_dois_docx()[indice])
    assert re.search(r'<w:pgSz w:w="11906" w:h="16838"', xml)
    margens = re.search(r"<w:pgMar [^>]*/>", xml).group(0)
    for lado, valor in (("top", 1701), ("left", 1701), ("bottom", 1134), ("right", 1134)):
        assert f'w:{lado}="{valor}"' in margens


@pytest.mark.parametrize("indice", [0, 1])
def test_estilos_em_arial_sem_tema(indice):
    documento = docx.Document(io.BytesIO(_os_dois_docx()[indice]))
    for nome in ("Normal", "Heading 1"):
        fontes = documento.styles[nome].element.rPr.rFonts
        for atributo in ("ascii", "hAnsi", "eastAsia", "cs"):
            assert fontes.get(qn(f"w:{atributo}")) == "Arial", (nome, atributo)
        assert not [a for a in fontes.attrib if "heme" in a], nome
    normal = documento.styles["Normal"]
    assert normal.font.size == Pt(12)
    assert normal.paragraph_format.space_before == Pt(0)
    assert normal.paragraph_format.space_after == Pt(6)
    titulo = documento.styles["Heading 1"]
    assert titulo.font.size == Pt(14)
    assert titulo.font.bold is True
    cor = titulo.element.rPr.find(qn("w:color"))
    assert cor is not None
    assert cor.get(qn("w:val")) == "000000"
    assert cor.get(qn("w:themeColor")) is None


def test_cabecalho_de_pagina_vazio():
    for dados in _os_dois_docx():
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            for nome in z.namelist():
                if nome.startswith("word/header"):
                    assert "<w:t" not in z.read(nome).decode("utf-8")


def test_identificacao_em_cada_prova():
    textos = paragrafos(_os_dois_docx()[0])
    for rotulo in ("Professor: Ana Souza", "Aluno: ", "Matrícula: ", "Data: ", "Nota: "):
        assert sum(1 for t in textos if t.startswith(rotulo)) == 2, rotulo
    assert not any(t.startswith("Nome: ") for t in textos)


def test_linhas_cabem_na_largura_util():
    """Arial 12: sublinhado ≈ 0,235 cm; área útil = 21 − 3 − 2 = 16 cm."""
    from backend.app.services.exportacao.renderizacao import _LINHA, _LINHA_CAMPO

    largura_util_cm = 16.0
    largura_sublinhado_cm = 0.556 * 12 / 72 * 2.54
    assert len(_LINHA) * largura_sublinhado_cm < largura_util_cm
    assert (
        len("Matrícula: ") * 0.25 + len(_LINHA_CAMPO) * largura_sublinhado_cm
        < largura_util_cm
    )


# --- contexto em 10 pt, enunciado justificado, alternativas com recuo ---

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Twips

from backend.app.services.exportacao.renderizacao import separar_contexto

CONTEXTO = "Uma rede de sensores envia leituras a cada 5 s para um servidor central."
COMANDO = "Qual estrutura organiza as leituras na ordem de chegada?"


def _paragrafos_doc(dados: bytes):
    return docx.Document(io.BytesIO(dados)).paragraphs


def _prova_um_item(item):
    return renderizar_conteudo_puro(CABECALHO, prova("A", [item]), prova("B", [item]))


def test_separar_contexto():
    assert separar_contexto(f"{CONTEXTO}\n\n{COMANDO}", CONTEXTO) == (CONTEXTO, COMANDO)
    assert separar_contexto(COMANDO, None) == (None, COMANDO)
    assert separar_contexto(COMANDO, "") == (None, COMANDO)
    assert separar_contexto(f"Outro.\n\n{COMANDO}", CONTEXTO) == (
        None,
        f"Outro.\n\n{COMANDO}",
    )


def test_contexto_em_10_e_resto_em_12_justificados():
    item = objetiva(3, f"{CONTEXTO}\n\n{COMANDO}", list("abcde"), contexto=CONTEXTO)
    ps = _paragrafos_doc(_prova_um_item(item))
    i = next(i for i, p in enumerate(ps) if p.text == f"3. {CONTEXTO}")
    contexto, comando = ps[i], ps[i + 1]
    assert comando.text == COMANDO
    # O texto volta igual, com a quebra de parágrafo no lugar do "\n\n".
    assert (
        contexto.text.removeprefix("3. ") + "\n\n" + comando.text
        == f"{CONTEXTO}\n\n{COMANDO}"
    )
    assert contexto.runs[0].font.size is None  # o número fica em 12
    assert all(r.font.size == Pt(10) for r in contexto.runs[1:])
    assert all(r.font.size is None for r in comando.runs)
    assert contexto.alignment == comando.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY


def test_questao_sem_contexto_toda_em_12():
    item = objetiva(1, COMANDO, list("abcde"))
    ps = _paragrafos_doc(_prova_um_item(item))
    enunciado = next(p for p in ps if p.text == f"1. {COMANDO}")
    assert all(r.font.size is None for r in enunciado.runs)
    assert enunciado.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY


def test_enunciado_sem_o_prefixo_sai_inteiro_em_12():
    enunciado = f"Cenário reescrito.\n\n{COMANDO}"
    item = objetiva(1, enunciado, list("abcde"), contexto=CONTEXTO)
    textos = paragrafos(_prova_um_item(item))
    assert f"1. {enunciado}" in textos


def test_contexto_vazio_e_ignorado():
    item = objetiva(1, COMANDO, list("abcde"), contexto="")
    textos = paragrafos(_prova_um_item(item))
    assert f"1. {COMANDO}" in textos
    assert "1. " not in textos


def test_contexto_com_formula_em_destaque():
    contexto = r"A posição é dada por \[x = x_0 + v t\] em metros."
    item = objetiva(1, f"{contexto}\n\n{COMANDO}", list("abcde"), contexto=contexto)
    dados = _prova_um_item(item)
    assert "<m:oMathPara" in _documento_xml(dados)
    ps = _paragrafos_doc(dados)
    inicio = next(i for i, p in enumerate(ps) if p.text.startswith("1. A posição"))
    fim = next(i for i, p in enumerate(ps) if p.text == COMANDO)
    for p in ps[inicio:fim]:
        assert p.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY
        assert all(r.font.size == Pt(10) for r in p.runs if r.text and r.text != "1. ")


def test_alternativas_a_esquerda_com_recuo():
    item = objetiva(1, COMANDO, ["fila", "pilha", "vetor", "grafo", "árvore"])
    ps = _paragrafos_doc(_prova_um_item(item))
    alternativa = next(p for p in ps if p.text == "A) fila")
    assert alternativa.alignment is None
    assert alternativa.paragraph_format.left_indent == Twips(283)


def test_metadados_trecho_base_em_10_e_sem_justificar():
    dados = renderizar_metadados(
        CABECALHO,
        gabarito("A", [item_objetivo()]),
        gabarito("B", [item_objetivo()]),
        VERIFICACAO,
        auditoria(),
    )
    ps = _paragrafos_doc(dados)
    trechos = [p for p in ps if p.text.startswith("Trecho-base: ")]
    assert trechos
    assert all(r.font.size == Pt(10) for p in trechos for r in p.runs)
    assert all(p.alignment is None for p in ps)


def test_metadados_trecho_da_auditoria_em_10():
    achado = Achado(
        risco=RiscoAuditoria.CORRETA_NAO_UNICA,
        alvo="C",
        localizacao="página 7",
        trecho_fonte="o material também sustenta C",
        proposta_ajuste="Reescreva C.",
    )
    dados = renderizar_metadados(
        CABECALHO,
        gabarito("A", [item_objetivo()]),
        gabarito("B", [item_objetivo()]),
        VERIFICACAO,
        auditoria([QuestaoAuditada(7, [achado])], auditadas=10),
    )
    trechos = [p for p in _paragrafos_doc(dados) if p.text.startswith("Trecho: ")]
    assert trechos
    assert all(r.font.size == Pt(10) for p in trechos for r in p.runs)
