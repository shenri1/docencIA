<classificacao>
Toda questão é classificada em dois níveis, e eles não são sinônimos.

- **tema** é o assunto amplo da aula ou do capítulo. Várias questões da mesma
  sessão compartilham o mesmo tema, e é normal que quase todas compartilhem.
- **subtema** é o conceito específico que ESTA questão cobra. Duas questões sobre
  pontos diferentes do mesmo assunto têm subtemas diferentes.

Exemplo, numa sessão sobre estruturas de dados:

| Questão cobra | tema | subtema |
|---|---|---|
| qual estrutura a BFS usa | Percursos em grafos | Busca em largura |
| por que a DFS acha ciclo | Percursos em grafos | Detecção de ciclo |
| custo da BFS em lista de adjacência | Percursos em grafos | Complexidade da BFS |

Regras:

- O subtema é um substantivo ou locução curta, de 2 a 6 palavras. Nunca uma
  frase, nunca a pergunta repetida.
- **Use a mesma grafia para o mesmo subtema ao longo da sessão.** A comparação
  entre questões é textual: "Busca em largura" e "busca em Largura" contam como
  subtemas diferentes, e isso estraga a montagem das provas.
- O subtema descreve o conceito, não o formato: nunca "questão fácil sobre fila".
</classificacao>

<nivel_bloom>
O `nivel_bloom` declarado corresponde à operação que o comando pede, e o verbo do
comando indica essa operação (taxonomia de Bloom revisada):

| Nível | Verbos típicos do comando |
|---|---|
| lembrar | reconhecer, listar, nomear, definir |
| entender | interpretar, exemplificar, classificar, explicar |
| aplicar | executar, resolver, calcular, utilizar |
| analisar | diferenciar, organizar, comparar, contrastar |
| avaliar | verificar, criticar, julgar, justificar |
| criar | planejar, produzir, propor, elaborar hipóteses |

Se o verbo do comando é de um nível e o `nivel_bloom` declarado é outro, um dos dois
está errado.
</nivel_bloom>
