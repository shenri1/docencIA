"""Cálculo de distribuição de questões — Núcleo Determinístico, nunca chama LLM.

Converte percentuais em contagens inteiras pelo método do maior resto. Função
pura: sem I/O, sem banco, sem rede. O resultado é auditado, e é por
isso que o cálculo inteiro é feito em aritmética de inteiros.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain import FaixaDificuldade
from backend.app.exceptions import ParametrosInconsistentesException

# Empate de fracionário resolve pela faixa mais difícil: o viés favorece
# 
_ORDEM_DESEMPATE = {
    FaixaDificuldade.DIFICIL: 0,
    FaixaDificuldade.MEDIA: 1,
    FaixaDificuldade.FACIL: 2,
}


@dataclass(frozen=True)
class DistribuicaoQuestoes:
    faceis: int
    medias: int
    dificeis: int

    def total(self) -> int:
        return self.faceis + self.medias + self.dificeis

    def itens(self) -> list[tuple[FaixaDificuldade, int]]:
        """O laço itera sobre isto: "gere N questões da faixa X".
        Sem este método, cada chamador reconstruiria o mapeamento à mão."""
        return [
            (FaixaDificuldade.FACIL, self.faceis),
            (FaixaDificuldade.MEDIA, self.medias),
            (FaixaDificuldade.DIFICIL, self.dificeis),
        ]


def calcular_distribuicao(n: int, p_f: int, p_m: int, p_d: int) -> DistribuicaoQuestoes:
    """Método do maior resto, com desempate por dificuldade."""
    if p_f + p_m + p_d != 100 or min(p_f, p_m, p_d) < 0:
        # Guarda de pré-condição, não duplicação da impede que um
        # chamador que pulou validar_distribuicao gere um banco errado em
        # silêncio. O teste de negativo não é redundante com a soma: -10/60/50
        # soma 100 e produziria divmod(-100, 100) == (-1, 0), ou seja, uma
        # contagem negativa com total() correto — errado sem parecer errado.
        raise ParametrosInconsistentesException(p_f, p_m, p_d)
    if n < 1:
        # Erro de programação do chamador, não regra de negócio do docente —
        # por isso ValueError, e não uma exceção de domínio com status HTTP.
        raise ValueError(f"n deve ser ao menos 1, recebido {n}")

    # divmod em inteiros: o piso e o NUMERADOR da parte fracionária saem
    # exatos. Em float, 47 * 10 / 100 == 4.7000000000000002, e o desempate
    # passaria a depender de representação binária.
    pisos: dict[FaixaDificuldade, int] = {}
    fracionarios: dict[FaixaDificuldade, int] = {}
    for faixa, percentual in (
        (FaixaDificuldade.FACIL, p_f),
        (FaixaDificuldade.MEDIA, p_m),
        (FaixaDificuldade.DIFICIL, p_d),
    ):
        pisos[faixa], fracionarios[faixa] = divmod(n * percentual, 100)

    # A soma de três partes fracionárias, cada uma menor que 1, nunca chega a
    # 3 — então o resto é 0, 1 ou 2 e uma única passada basta.
    resto = n - sum(pisos.values())
    ordenadas = sorted(
        pisos, key=lambda faixa: (-fracionarios[faixa], _ORDEM_DESEMPATE[faixa])
    )
    for faixa in ordenadas[:resto]:
        pisos[faixa] += 1

    return DistribuicaoQuestoes(
        faceis=pisos[FaixaDificuldade.FACIL],
        medias=pisos[FaixaDificuldade.MEDIA],
        dificeis=pisos[FaixaDificuldade.DIFICIL],
    )
