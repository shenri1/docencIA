"""Formatação de valores e unidades — Núcleo Determinístico.

3 algarismos significativos nas alternativas, vírgula decimal, notação
científica fora de [1e-3, 1e6). A unidade vem do pint em LaTeX e é conferida
contra o subconjunto da unidade fora dele não tem representação.
"""

from __future__ import annotations

from backend.app.services.calculo_item.avaliador import UREG
from backend.app.services.notacao import comandos_fora_do_subconjunto

_LIMITE_INFERIOR = -3
_LIMITE_SUPERIOR = 6


def formatar_valor(x: float, algarismos: int = 3, aparar: bool = False) -> str:
    if x == 0:
        return "0"
    sinal = "-" if x < 0 else ""
    mantissa, expoente = f"{abs(x):.{algarismos - 1}e}".split("e")
    e = int(expoente)  # depois do arredondamento: 9,996 → 1,00e+01
    if _LIMITE_INFERIOR <= e < _LIMITE_SUPERIOR:
        casas = algarismos - 1 - e
        # Acima de `algarismos` dígitos inteiros o valor também é arredondado:
        # 123456 → 123000, para a alternativa ter 3 algarismos significativos.
        valor = round(abs(x), casas) if casas < 0 else abs(x)
        texto = f"{valor:.{max(0, casas)}f}"
        if aparar and "." in texto:
            texto = texto.rstrip("0").rstrip(".")
        return sinal + texto.replace(".", "{,}")
    if aparar:
        mantissa = mantissa.rstrip("0").rstrip(".")
    return f"{sinal}{mantissa.replace('.', '{,}')} \\times 10^{{{e}}}"


def unidade_latex(unidade: str) -> str | None:
    """ "" se a grandeza é adimensional; None se o pint não escreve a unidade com
    o subconjunto."""
    if not unidade.strip() or unidade.strip() == "dimensionless":
        return ""
    try:
        texto = f"{UREG.Unit(unidade):~L}"
    except Exception:  # noqa: BLE001
        return None
    return None if comandos_fora_do_subconjunto(texto) else texto


def valor_com_unidade(valor: str, unidade_ltx: str) -> str:
    return valor if not unidade_ltx else f"{valor}\\ {unidade_ltx}"
