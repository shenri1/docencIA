"""Reverificação sem LLM das questões de cálculo: recalcula a
partir de `estrutura_formato` e compara com as alternativas gravadas. É o que
cumpre o critério do as alternativas são reproduzíveis sem LLM."""

from __future__ import annotations

from backend.app.services.calculo_item.montagem import CalculoNaoMontavel, calcular


def reverificar(
    estrutura: dict, alternativas: list[tuple[str, str, bool]]
) -> list[tuple[str, str]]:
    """`alternativas`: (letra, texto, correta). Devolve (letra, detalhe) de cada
    alternativa divergente; vazia se tudo bate. Nunca levanta: estrutura que não
    recalcula (banco editado à mão, versão nova do pint) vira achado."""
    try:
        calculado = calcular(estrutura)
    except (CalculoNaoMontavel, KeyError, TypeError, ValueError) as exc:
        return [("A", f"a estrutura gravada não recalcula: {exc}")]
    esperada_correta = calculado.correta.alternativa
    esperados_erros = sorted(e.alternativa for e in calculado.erros)
    achados: list[tuple[str, str]] = []
    gravada_correta = [t for _, t, c in alternativas if c]
    if gravada_correta != [esperada_correta]:
        letra = next((letra for letra, _, c in alternativas if c), "A")
        achados.append(
            (letra, f"a correta gravada difere da recalculada ({esperada_correta})")
        )
    gravados_erros = sorted(t for _, t, c in alternativas if not c)
    if gravados_erros != esperados_erros:
        for letra, texto, correta in alternativas:
            if not correta and texto not in esperados_erros:
                achados.append(
                    (
                        letra,
                        f"o distrator gravado ({texto}) não é nenhum dos recalculados",
                    )
                )
    return achados
