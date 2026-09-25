"""Montagem do prompt mestre — Núcleo Determinístico, nunca chama LLM.

Os módulos vivem em git e são lidos em tempo de execução. A montagem é pura:
os mesmos arquivos e os mesmos parâmetros produzem sempre o mesmo texto, e é
isso que permite gravar o resultado como registro de auditoria.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from backend.app.exceptions import PlaceholderNaoResolvidoException
from backend.app.prompt.parametros import ParametrosGeracao

DIRETORIO_MODULOS = Path(__file__).parent
# Delimitador duplo para não colidir com chaves do próprio texto.
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def carregar_modulos() -> list[tuple[str, str]]:
    """Ordem alfabética do nome do arquivo é a ordem de montagem — por isso o
    prefixo numérico."""
    return [
        (caminho.name, caminho.read_text(encoding="utf-8"))
        for caminho in sorted(DIRETORIO_MODULOS.glob("*.md"))
    ]


def calcular_hash(modulos: list[tuple[str, str]]) -> str:
    """SHA-256 do conteúdo concatenado. Detecta edição em disco sem versão
    nova, que faria o `conteudo` gravado mentir sobre o que seria enviado."""
    digestor = hashlib.sha256()
    for nome, conteudo in modulos:
        digestor.update(nome.encode("utf-8"))
        digestor.update(conteudo.encode("utf-8"))
    return digestor.hexdigest()


_PASTA_CRITICO = "critico"
# Módulos do Gerador reaproveitados pelo crítico: as regras de qualidade e a
# política de fontes têm uma única fonte de verdade.
_COMPARTILHADOS_COM_CRITICO = ("02_qualidade_alternativas.md", "03_politica_fontes.md")


def carregar_modulos_critico() -> list[tuple[str, str]]:
    """O caminho relativo entra no nome para que mover um arquivo entre pastas
    também mude o hash."""
    pasta = DIRETORIO_MODULOS / _PASTA_CRITICO
    return [
        (f"{_PASTA_CRITICO}/{caminho.name}", caminho.read_text(encoding="utf-8"))
        for caminho in sorted(pasta.glob("*.md"))
    ]


def carregar_modulos_versionados() -> list[tuple[str, str]]:
    """Tudo que o hash de versão cobre: Gerador e crítico. Sem o crítico aqui,
    editar o prompt de revisão não exigiria versão nova."""
    return carregar_modulos() + carregar_modulos_critico()


def _injetar(texto: str, params: ParametrosGeracao) -> str:
    valores = params.como_dicionario()

    def substituir(casamento: re.Match[str]) -> str:
        return valores.get(casamento.group(1), casamento.group(0))

    montado = _PLACEHOLDER.sub(substituir, texto)

    restantes = sorted(set(_PLACEHOLDER.findall(montado)))
    if restantes:
        raise PlaceholderNaoResolvidoException(restantes)
    return montado


def montar_sistema(params: ParametrosGeracao) -> str:
    return _injetar(
        "\n\n".join(conteudo for _, conteudo in carregar_modulos()), params
    )


def montar_sistema_critico(params: ParametrosGeracao) -> str:
    """Módulos do crítico + qualidade + fontes. Persona do gerador e few-shot
    ficam de fora: o crítico já recebe o rascunho, que é o exemplo relevante."""
    do_gerador = dict(carregar_modulos())
    partes = [conteudo for _, conteudo in carregar_modulos_critico()] + [
        do_gerador[nome] for nome in _COMPARTILHADOS_COM_CRITICO
    ]
    return _injetar("\n\n".join(partes), params)
