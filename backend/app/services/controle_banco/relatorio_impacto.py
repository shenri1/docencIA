"""Relatório de impacto — Núcleo Determinístico, função pura, nunca chama LLM.

Cada exclusão, substituição aceita e congelamento gera um relatório com
N final, contagem por faixa e observação sobre desvio de pF/pM/pD. Desde as
discursivas o banco é misto, e pF/pM/pD vale para cada tipo separadamente: cada
tipo é medido contra o mesmo percentual, com o seu próprio N.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from backend.app.domain import FaixaDificuldade, TipoQuestao

_DUAS_CASAS = Decimal("0.01")

# O requisito fala em "observação sobre desvio" sem fixar limiar; 5 pontos
# percentuais é escolha. A fronteira exata NÃO alerta.
TOLERANCIA_PONTOS = 5


@dataclass(frozen=True)
class ImpactoTipo:
    n: int
    contagem_por_faixa: dict[FaixaDificuldade, int]
    # Pontos percentuais. None quando o tipo foi pedido e não tem questão ativa.
    desvio_por_faixa: dict[FaixaDificuldade, Decimal | None]
    alerta_desvio: bool


@dataclass(frozen=True)
class Impacto:
    n_final: int
    por_tipo: dict[TipoQuestao, ImpactoTipo]
    alerta_desvio: bool


def _desvio(c: int, n: int, p: int) -> Decimal:
    return (Decimal(100 * c) / Decimal(n) - Decimal(p)).quantize(
        _DUAS_CASAS, rounding=ROUND_HALF_EVEN
    )


def calcular_impacto(
    contagens: dict[TipoQuestao, dict[FaixaDificuldade, int]],
    tipos_pedidos: set[TipoQuestao],
    p_f: int,
    p_m: int,
    p_d: int,
) -> Impacto:
    """`contagens` são das questões ATIVA. `tipos_pedidos` são os tipos com
    n_alvo > 0 — só eles entram no relatório, porque tipo não pedido não tem do
    que desviar."""
    percentuais = {
        FaixaDificuldade.FACIL: p_f,
        FaixaDificuldade.MEDIA: p_m,
        FaixaDificuldade.DIFICIL: p_d,
    }
    # Itera sobre TipoQuestao, não sobre o set: a ordem do relatório é a do
    # enum, e não a ordem de iteração de um set, que varia.
    por_tipo: dict[TipoQuestao, ImpactoTipo] = {}
    for tipo in TipoQuestao:
        if tipo not in tipos_pedidos:
            continue
        do_tipo = contagens.get(tipo, {})
        contagem = {faixa: do_tipo.get(faixa, 0) for faixa in percentuais}
        n = sum(contagem.values())
        if n == 0:
            # Tipo pedido e sem nenhuma ativa: não há proporção para medir, e é
            # exatamente o que o docente precisa ver.
            por_tipo[tipo] = ImpactoTipo(
                n=0,
                contagem_por_faixa=contagem,
                desvio_por_faixa=dict.fromkeys(percentuais),
                alerta_desvio=True,
            )
            continue
        # Aritmética inteira no alerta: |100·c − p·n| > 5·n, sem divisão. Ponto
        # flutuante na fronteira exata produziria alerta irreproduzível à mão.
        alerta = any(
            abs(100 * contagem[faixa] - p * n) > TOLERANCIA_PONTOS * n
            for faixa, p in percentuais.items()
        )
        por_tipo[tipo] = ImpactoTipo(
            n=n,
            contagem_por_faixa=contagem,
            desvio_por_faixa={
                faixa: _desvio(contagem[faixa], n, p)
                for faixa, p in percentuais.items()
            },
            alerta_desvio=alerta,
        )
    return Impacto(
        n_final=sum(t.n for t in por_tipo.values()),
        por_tipo=por_tipo,
        alerta_desvio=any(t.alerta_desvio for t in por_tipo.values()),
    )
