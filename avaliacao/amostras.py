"""Questões do banco → amostras do RAGAS — puro, sem banco, rede nem LLM.

Só lê atributos, então aceita o ORM ou qualquer objeto com a mesma forma. Fica
fora de `backend/app/` de propósito: o RAGAS usa um LLM como juiz, e a regra
arquitetural proíbe LLM no caminho da API.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

MOTIVO_SEM_CONTEXTO = "sem contexto"


@dataclass
class Montagem:
    amostras: list[dict] = field(default_factory=list)
    # `ids[i]` é a questão de `amostras[i]`: o RAGAS devolve as notas na ordem.
    ids: list[int] = field(default_factory=list)
    puladas: list[tuple[int, str]] = field(default_factory=list)


def contextos_das_fontes(questao) -> list[str]:
    """Modo 1: os trechos que a própria questão cita, sem vazios nem repetidos."""
    vistos: dict[str, None] = {}
    for fonte in questao.fontes_internas:
        trecho = fonte.trecho_base.strip()
        if trecho:
            vistos.setdefault(trecho)
    return list(vistos)


def _valor(enum_ou_texto) -> str:
    """Aceita o enum do app, o nome gravado no Postgres ("CALCULO") ou o valor.
    Não importa `backend.app`: este pacote roda num Python que o app não roda."""
    return str(getattr(enum_ou_texto, "value", enum_ou_texto)).lower()


def _resposta(questao) -> str:
    partes = [questao.enunciado]
    justificativa = questao.justificativa

    if _valor(questao.tipo) == "discursiva":
        aspectos = sorted(questao.aspectos, key=lambda a: a.ordem)
        if aspectos:
            partes.append(
                "Aspectos esperados:\n" + "\n".join(f"- {a.texto}" for a in aspectos)
            )
    elif _valor(questao.formato) == "calculo":
        # O resultado e a resolução saem do avaliador determinístico, não do
        # material. O que o material precisa sustentar é a fórmula e o cenário.
        estrutura = (justificativa.estrutura_formato if justificativa else None) or {}
        if estrutura.get("formula_citada"):
            partes.append(f"Fórmula utilizada: {estrutura['formula_citada']}")
    else:
        correta = next((a for a in questao.alternativas if a.correta), None)
        if correta is not None:
            partes.append(f"Gabarito: {correta.letra}) {correta.texto}")
        if justificativa and justificativa.justificativa_correta:
            partes.append(justificativa.justificativa_correta)

    return "\n".join(partes)


def montar_amostra(questao, contextos: list[str]) -> dict:
    return {
        "user_input": questao.tema or questao.enunciado,
        "response": _resposta(questao),
        "retrieved_contexts": contextos,
    }


def montar_amostras(
    questoes: Iterable,
    contextos_por_questao: Mapping[int, list[str]] | None = None,
) -> Montagem:
    """`contextos_por_questao` é o Modo 2 (top-k refeito); sem ele, Modo 1."""
    montagem = Montagem()
    for questao in questoes:
        if contextos_por_questao is not None and questao.id in contextos_por_questao:
            contextos = contextos_por_questao[questao.id]
        else:
            contextos = contextos_das_fontes(questao)
        if not contextos:
            montagem.puladas.append((questao.id, MOTIVO_SEM_CONTEXTO))
            continue
        montagem.amostras.append(montar_amostra(questao, contextos))
        montagem.ids.append(questao.id)
    return montagem
