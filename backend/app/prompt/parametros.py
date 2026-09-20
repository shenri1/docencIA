"""Parâmetros injetados no prompt mestre.

Todos os valores chegam **já validados e já calculados**. A validação  é de `validar_distribuicao`; o cálculo das contagens inteiras é . Este módulo formata e injeta — nunca decide nada.
"""

from __future__ import annotations

from dataclasses import dataclass

_AUSENTE_FEMININO = "não informada"
_AUSENTE_MASCULINO = "não informado"


@dataclass(frozen=True)
class ParametrosGeracao:
    disciplina: str
    periodo: str
    area_do_conhecimento: str | None
    tema_escopo: str | None
    k_alternativas: int
    n_faceis: int
    n_medias: int
    n_dificeis: int

    def como_dicionario(self) -> dict[str, str]:
        """Campos opcionais nulos viram texto legível: deixar "None" no prompt
        faria o modelo tratar a string como conteúdo."""
        return {
            "disciplina": self.disciplina,
            "periodo": self.periodo,
            "area_do_conhecimento": self.area_do_conhecimento or _AUSENTE_FEMININO,
            "tema_escopo": self.tema_escopo or _AUSENTE_MASCULINO,
            "k_alternativas": str(self.k_alternativas),
            "n_faceis": str(self.n_faceis),
            "n_medias": str(self.n_medias),
            "n_dificeis": str(self.n_dificeis),
        }
