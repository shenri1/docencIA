"""Renderização DOCX — Núcleo Determinístico, puro.

Recebe as estruturas que as já montam e devolve bytes. Não
abre sessão de banco, não decide conteúdo, não chama LLM.

Fidelidade: texto persistido entra sem `strip`, sem troca de aspas, sem
capitalização. Quebra de linha dentro do texto vira quebra de linha no DOCX, que
é o que o python-docx faz ao atribuir texto a um run.

Reprodutibilidade: medido com python-docx 1.2.0, o mesmo conteúdo renderizado
duas vezes muda SÓ a data das entradas do zip. `normalizar_zip` fixa essa data,
e o sha256 do arquivo entregue vira prova conferível com `sha256sum`. Por isso
nenhuma data entra no documento.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import docx
from docx.enum.text import WD_BREAK

from backend.app.services.critico.auditor_service import ResumoAuditoria
from backend.app.services.geracao.formatos import LETRAS_ITEM
from backend.app.services.provas.gabarito import FonteGabarito, Gabarito, ItemGabarito
from backend.app.services.provas.leitura import ItemLido, ProvaLida
from backend.app.services.provas.verificacao import Verificacao

LINHAS_RESPOSTA_DISCURSIVA = 8
_LINHA = "_" * 90
# Menor data que o formato zip representa.
_DATA_FIXA = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Cabecalho:
    disciplina: str
    periodo: str
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


def _salvar(documento) -> bytes:
    buffer = io.BytesIO()
    documento.save(buffer)
    return normalizar_zip(buffer.getvalue())


def _paragrafo(documento, *partes: str):
    """Um parágrafo com um run por parte: o texto persistido fica num run só,
    sem concatenação que o transforme."""
    paragrafo = documento.add_paragraph()
    for parte in partes:
        paragrafo.add_run(parte)
    return paragrafo


def _quebra_de_pagina(documento) -> None:
    documento.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _item_da_prova(documento, item: ItemLido) -> None:
    _paragrafo(documento, f"{item.posicao}. ", item.enunciado)
    if item.alternativas:
        for alternativa in item.alternativas:
            _paragrafo(documento, f"{alternativa.letra}) ", alternativa.texto)
    else:
        for _ in range(LINHAS_RESPOSTA_DISCURSIVA):
            _paragrafo(documento, _LINHA)


def renderizar_conteudo_puro(
    cabecalho: Cabecalho, prova_a: ProvaLida, prova_b: ProvaLida
) -> bytes:
    """Provas A e B, sem gabarito e sem fontes internas. Não tem como vazar: a
    `ProvaLida` não tem campo para nada disso."""
    documento = docx.Document()
    for indice, prova in enumerate((prova_a, prova_b)):
        if indice:
            _quebra_de_pagina(documento)
        documento.add_heading(
            f"{cabecalho.disciplina} — {cabecalho.periodo} — Prova {prova.versao}",
            level=1,
        )
        _paragrafo(documento, "Nome: ", _LINHA)
        _paragrafo(documento, "Data: ", "____/____/________")
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
        _paragrafo(documento, "Justificativa: ", item.justificativa_correta)
    for invalidacao in item.invalidacoes:
        rotulo = f"{invalidacao.letra}) " if invalidacao.letra else "— "
        _paragrafo(documento, rotulo, invalidacao.motivo)
    item_atual = None
    for aspecto in item.aspectos:
        if aspecto.item is not None and aspecto.item != item_atual:
            item_atual = aspecto.item
            _paragrafo(documento, f"Item {LETRAS_ITEM[aspecto.item - 1]})")
        _paragrafo(documento, f"{aspecto.ordem}. ", aspecto.texto)
        _paragrafo(documento, "Fonte: ", _fonte_texto(aspecto.fonte))
        if aspecto.fonte.trecho_base is not None:
            _paragrafo(documento, "Trecho-base: ", aspecto.fonte.trecho_base)
    if item.objetivo_cognitivo is not None:
        _paragrafo(documento, "Objetivo cognitivo: ", item.objetivo_cognitivo)
    for fonte in item.fontes:
        _paragrafo(documento, "Fonte: ", _fonte_texto(fonte))
        if fonte.trecho_base is not None:
            _paragrafo(documento, "Trecho-base: ", fonte.trecho_base)


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
            _paragrafo(
                documento, f"{achado.risco.value} — alternativa {achado.alvo}"
            )
            if achado.localizacao is not None:
                _paragrafo(documento, "Localização: ", achado.localizacao)
            if achado.trecho_fonte is not None:
                _paragrafo(documento, "Trecho: ", achado.trecho_fonte)
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
    documento.add_heading(
        f"{cabecalho.disciplina} — {cabecalho.periodo} — Metadados", level=1
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
