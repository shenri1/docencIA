<exemplos>

Os exemplos abaixo ilustram FORMA, não conteúdo. O que se reaproveita é o padrão de
construção do comando e dos aspectos, aplicado ao material da sessão atual.

<exemplo_1_questao_adequada>
Trechos fornecidos:
(P1, página 12): "A busca em largura visita todos os vértices a uma mesma distância da
origem antes de avançar, o que garante encontrar o caminho com menor número de arestas
em grafos não ponderados."
(P1, página 13): "A busca em largura mantém os vértices descobertos numa fila."

Enunciado: Explique por que a busca em largura encontra, em grafos não ponderados, o
caminho com menor número de arestas a partir da origem.

Aspectos esperados:
1. Os vértices são visitados por camadas de distância crescente. — P1, página 12
2. A fila mantém a ordem de descoberta, o que preserva as camadas. — P1, página 13
3. A garantia vale porque todas as arestas têm o mesmo peso. — P1, página 12

Por que é adequada: comando único ("explique"), recorte delimitado ("grafos não
ponderados"), e cada aspecto é algo que se verifica na resposta e tem trecho próprio.
</exemplo_1_questao_adequada>

<exemplo_2_violacao_corrigida>
ANTES:
Enunciado: Fale sobre a busca em largura, que usa fila e visita por camadas.
Aspectos: "a resposta é completa"; "o aluno domina o conteúdo".

Violações:
1. "Fale sobre" não é comando operacional; o recorte é o tema inteiro.
2. O enunciado entrega a resposta ("usa fila e visita por camadas").
3. Os aspectos não são observáveis numa resposta e não têm fonte.

DEPOIS:
Enunciado: Compare a busca em largura e a busca em profundidade quanto à estrutura
auxiliar que cada uma usa e ao efeito dessa escolha na ordem de visita.
Aspectos: "a largura usa fila" (P1, página 13); "a profundidade usa pilha ou recursão"
(P1, página 15); "a fila produz visita por camadas de distância" (P1, página 12).
</exemplo_2_violacao_corrigida>

<exemplo_3_estudo_de_caso_com_itens>
Trechos fornecidos: os mesmos do exemplo 1, e (P1, página 15): "Em grafos ponderados,
o algoritmo de Dijkstra encontra o caminho de menor custo total."

Contexto: Uma empresa de entregas modela os pontos de uma cidade como vértices e as
ruas como arestas. Hoje cada rua conta como uma ligação, e a equipe usa busca em
largura para planejar as rotas. A empresa quer passar a considerar o tempo de percurso
de cada rua, que varia de rua para rua.

a) Explique por que a busca em largura encontra hoje a rota com menos ruas.
   Aspectos: a visita é por camadas de distância (P1, página 12); a garantia vale
   porque todas as arestas têm o mesmo peso (P1, página 12).
b) Avalie se a busca em largura continua adequada quando cada rua tiver o seu tempo de
   percurso, e justifique.
   Aspectos: com pesos diferentes, menos arestas deixa de significar menor custo (P1,
   página 12); o caminho de menor custo total é o do algoritmo de Dijkstra (P1,
   página 15).

Por que é adequada: um contexto para os dois itens, cada item com um verbo e uma
operação diferente, e o b) pode ser respondido mesmo por quem errou o a).
</exemplo_3_estudo_de_caso_com_itens>

</exemplos>
