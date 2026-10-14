<exemplo_calculo>
Trechos: (P1, página 8) "Um corpo solto do repouso, desprezada a resistência do ar,
atinge o solo com velocidade v = sqrt(2 g h), em que g é a aceleração da gravidade e h
a altura da queda."

Faixa: fácil. K = 4.

{
  "tipo": "questao",
  "contexto": "Uma bola é solta do repouso do alto de um prédio, e a resistência do ar é desprezada.",
  "comando": "Qual a velocidade da bola ao chegar ao solo, dada a altura h da queda e a aceleração da gravidade g?",
  "dados": [
    {"simbolo": "g", "valor": 9.8, "unidade": "m/s**2"},
    {"simbolo": "h", "valor": 20, "unidade": "m"}
  ],
  "formula_citada": "v = sqrt(2 g h)",
  "expressao": "sqrt(2 * g * h)",
  "unidade_resultado": "m/s",
  "erros": [
    {"descricao": "esquece o fator 2 dentro da raiz", "expressao": "sqrt(g * h)"},
    {"descricao": "divide por 2 em vez de multiplicar", "expressao": "sqrt(g * h / 2)"},
    {"descricao": "põe o fator 2 fora da raiz", "expressao": "2 * sqrt(g * h)"}
  ],
  "objetivo_cognitivo": "aplicar a fórmula da velocidade de queda a um caso numérico",
  "fontes": [
    {"identificador_material": "P1", "localizacao": "página 8", "trecho_base": "v = sqrt(2 g h)"}
  ],
  "tema": "queda livre",
  "subtema": "velocidade final",
  "nivel_bloom": "aplicar"
}

Por que é adequada: o texto cita g e h pelo símbolo e não repete os valores; a fórmula é
copiada do trecho; cada erro é um deslize que o aluno comete e dá um valor diferente.
O sistema calcula a correta e os erros, escreve as alternativas e a resolução.
</exemplo_calculo>
