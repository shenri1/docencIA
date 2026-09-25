"""Montagem do prompt mestre — Núcleo Determinístico, nunca chama LLM.

Os módulos vivem em git e são lidos em tempo de execução. A montagem é pura:
os mesmos arquivos e os mesmos parâmetros produzem sempre o mesmo texto, e é
isso que permite gravar o resultado como registro de auditoria.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.app.domain import TipoQuestao
from backend.app.exceptions import PlaceholderNaoResolvidoException
from backend.app.prompt.parametros import ParametrosGeracao

DIRETORIO_MODULOS = Path(__file__).parent
# Delimitador duplo para não colidir com chaves do próprio texto.
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def calcular_hash(modulos: list[tuple[str, str]]) -> str:
    """SHA-256 do conteúdo concatenado. Detecta edição em disco sem versão
    nova, que faria o `conteudo` gravado mentir sobre o que seria enviado."""
    digestor = hashlib.sha256()
    for nome, conteudo in modulos:
        digestor.update(nome.encode("utf-8"))
        digestor.update(conteudo.encode("utf-8"))
    return digestor.hexdigest()


_PASTA_POR_TIPO = {
    TipoQuestao.OBJETIVA: "objetiva",
    TipoQuestao.DISCURSIVA: "discursiva",
}
# O crítico de cada tipo recebe o próprio módulo de revisão e as regras de
# qualidade do tipo, que têm uma única fonte de verdade: o módulo do Gerador.
_CRITICO_POR_TIPO = {
    TipoQuestao.OBJETIVA: (
        "critico/02_objetiva.md",
        "objetiva/02_qualidade_alternativas.md",
    ),
    TipoQuestao.DISCURSIVA: (
        "critico/03_discursiva.md",
        "discursiva/01_formato.md",
    ),
}


def _relativo(caminho: Path) -> str:
    return caminho.relative_to(DIRETORIO_MODULOS).as_posix()


def carregar_modulos(pasta: str) -> list[tuple[str, str]]:
    """Módulos de uma pasta, em ordem de nome — por isso o prefixo numérico. O
    caminho relativo entra no nome para que mover um arquivo mude o hash."""
    return [
        (_relativo(caminho), caminho.read_text(encoding="utf-8"))
        for caminho in sorted((DIRETORIO_MODULOS / pasta).glob("*.md"))
    ]


def carregar_modulos_versionados() -> list[tuple[str, str]]:
    """Tudo que o hash de versão cobre, em qualquer pasta: um módulo
    novo entra no hash sem ninguém precisar listá-lo."""
    caminhos = sorted(DIRETORIO_MODULOS.rglob("*.md"), key=_relativo)
    return [(_relativo(c), c.read_text(encoding="utf-8")) for c in caminhos]


def _injetar(texto: str, params: ParametrosGeracao) -> str:
    valores = params.como_dicionario()

    def substituir(casamento: re.Match[str]) -> str:
        return valores.get(casamento.group(1), casamento.group(0))

    montado = _PLACEHOLDER.sub(substituir, texto)

    restantes = sorted(set(_PLACEHOLDER.findall(montado)))
    if restantes:
        raise PlaceholderNaoResolvidoException(restantes)
    return montado


def montar_sistema(tipo: TipoQuestao, params: ParametrosGeracao) -> str:
    modulos = carregar_modulos("comum") + carregar_modulos(_PASTA_POR_TIPO[tipo])
    return _injetar("\n\n".join(conteudo for _, conteudo in modulos), params)


def montar_sistema_critico(tipo: TipoQuestao, params: ParametrosGeracao) -> str:
    """Revisor + revisão do tipo + qualidade do tipo + política de fontes.
    Persona do gerador e few-shot ficam de fora: o crítico já recebe o
    rascunho, que é o exemplo relevante."""
    todos = dict(carregar_modulos_versionados())
    revisao, qualidade = _CRITICO_POR_TIPO[tipo]
    nomes = ["critico/01_revisor.md", revisao, qualidade, "comum/02_politica_fontes.md"]
    return _injetar("\n\n".join(todos[nome] for nome in nomes), params)
