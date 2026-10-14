<notacao>
Fórmulas matemáticas e químicas vão em LaTeX, e só nele.

- Em linha: `\(...\)`. Em destaque, numa linha própria: `\[...\]`. Nunca use `$`.
- Use só: letras, dígitos, `+ - = < > ( ) [ ] , . / |`; `^` e `_`; `\frac`, `\sqrt`,
  `\sqrt[n]`; `\sum`, `\int`, `\prod`, `\lim` com limites; letras gregas;
  `\mathrm`, `\text`; `\cdot`, `\times`, `\pm`, `\leq`, `\geq`, `\neq`, `\approx`,
  `\infty`, `\partial`, `\Delta`; `\to`, `\rightarrow`, `\leftarrow`,
  `\rightleftharpoons`; `\left`, `\right`; matrizes `pmatrix` e `bmatrix`.
- Não use `\ce{}`, `align`, `\color`, `\href`, macros.
- Fórmula química: `\(\mathrm{H_2SO_4}\)`. Reação: `\(\mathrm{N_2 + 3H_2 \rightleftharpoons 2NH_3}\)`.
- No JSON, a barra invertida vai dobrada: `"\\frac{a}{b}"`. Uma barra só quebra a fórmula.
- Uma fórmula nunca ocupa mais de uma linha. Dentro de `\(...\)` não há quebra de linha.
- Use fórmula só quando o texto puro não der conta. "R$ 50,00" e unidades simples ficam em texto.

Exemplos:

- `A razão é \(\frac{a}{b}\) quando \(b \neq 0\).`
- `\[\int_{0}^{1} x^2 dx\]`
- `\(\mathrm{2H_2 + O_2 \rightarrow 2H_2O}\)`
</notacao>
