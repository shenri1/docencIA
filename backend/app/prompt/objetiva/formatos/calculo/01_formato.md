<formato_calculo>
Esta é uma questão de cálculo numérico. Você não calcula nada: propõe, e o sistema calcula.

Preencha, nesta ordem:
1. `contexto` e `comando`: o cenário e a pergunta. Refira-se aos dados pelo símbolo
   ("a altura h"), nunca pelo valor. O sistema imprime o bloco "Dados:".
2. `dados`: cada grandeza com `simbolo` (letras, dígitos e _, sem acento; não use sqrt,
   exp, ln, log10, sin, cos, tan, abs nem pi), `valor` numérico e `unidade` na sintaxe
   do Python/pint: "m/s**2", "mol/L", "kg". Grandeza sem dimensão: "". Prefira kelvin a
   graus Celsius. Constantes (g, R, N_A) também vão em `dados`.
3. `formula_citada`: a fórmula copiada literalmente do trecho, como está escrita nele.
4. `expressao`: a conta em sintaxe de Python, só com os símbolos de `dados` e `pi`:
   `+ - * / **`, parênteses e as funções sqrt, exp, ln, log10, sin, cos, tan, abs.
   Ângulos: informe a unidade `degree` ou `radian` no dado.
5. `unidade_resultado`: a unidade da resposta, na mesma sintaxe.
6. `erros`: exatamente K − 1 erros típicos de aluno (unidade não convertida, fórmula
   trocada, etapa esquecida, sinal trocado). Cada um com `descricao` e a `expressao`
   que o aluno resolveria. Cada erro deve dar um valor diferente dos outros e do correto.

Não escreva o valor do resultado, nem alternativas, nem o valor dos dados no texto.
Se o material não traz a fórmula necessária, declare insuficiência de fonte e diga
qual fórmula faltou.

Faixas: fácil, uma fórmula aplicada direto; média, duas etapas ou uma conversão de
unidade; difícil, um cenário com várias etapas.
</formato_calculo>
