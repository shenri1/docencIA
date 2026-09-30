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
    disciplina="Algoritmos", periodo="2026.2", versao_banco="v1", revisao_banco=3
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


def objetiva(posicao: int, enunciado: str, textos: list[str]) -> ItemLido:
    return ItemLido(
        posicao=posicao,
        numero=posicao,
        tipo=TipoQuestao.OBJETIVA,
        faixa_dificuldade=FaixaDificuldade.MEDIA,
        enunciado=enunciado,
        alternativas=[
            AlternativaLida(letra, texto) for letra, texto in zip("ABCDE", textos)
        ],
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
    a = prova("A", [objetiva(1, "Qual estrutura a BFS usa?", ["fila", "pilha", "vetor", "grafo", "árvore"])])
    b = prova("B", [objetiva(1, "Qual estrutura a DFS usa?", ["pilha", "fila", "vetor", "grafo", "árvore"])])
    textos = paragrafos(renderizar_conteudo_puro(CABECALHO, a, b))

    juntos = "\n".join(textos)
    assert juntos.index("Prova A") < juntos.index("Qual estrutura a BFS usa?")
    assert juntos.index("Qual estrutura a BFS usa?") < juntos.index("Prova B")
    assert "A) fila" in textos
    assert "B) pilha" in textos


def test_texto_persistido_sai_identico():
    """Fidelidade: sem strip, sem troca de aspas, com quebra de linha."""
    enunciado = '  Considere o grafo "G":\nqual percurso usa fila?  '
    a = prova("A", [objetiva(1, enunciado, ["fila", "pilha", "vetor", "grafo", "árvore"])])
    b = prova("B", [objetiva(1, "outra", ["fila", "pilha", "vetor", "grafo", "árvore"])])
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
        CABECALHO, gabarito("A", [item_objetivo()]), gabarito("B", [item_objetivo()]),
        VERIFICACAO, auditoria(),
    )
    time.sleep(2.1)
    outra = renderizar_metadados(
        CABECALHO, gabarito("A", [item_objetivo()]), gabarito("B", [item_objetivo()]),
        VERIFICACAO, auditoria(),
    )
    assert uma == outra
