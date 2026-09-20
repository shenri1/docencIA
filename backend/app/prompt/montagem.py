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


def montar_sistema(params: ParametrosGeracao) -> str:
    modulos = carregar_modulos()
    texto = "\n\n".join(conteudo for _, conteudo in modulos)
    valores = params.como_dicionario()

    def substituir(casamento: re.Match[str]) -> str:
        return valores.get(casamento.group(1), casamento.group(0))

    montado = _PLACEHOLDER.sub(substituir, texto)

    restantes = sorted(set(_PLACEHOLDER.findall(montado)))
    if restantes:
        raise PlaceholderNaoResolvidoException(restantes)
    return montado
