<exemplos>

Os exemplos abaixo ilustram FORMA, não conteúdo. O domínio deles é irrelevante: o que
se reaproveita é o padrão de construção do contexto, das alternativas e da fonte,
aplicado ao material da sessão atual.

<exemplo_1_questao_adequada>
Trecho fornecido (P1, página 12): "A busca em largura visita todos os vértices a uma
mesma distância da origem antes de avançar, o que garante encontrar o caminho com menor
número de arestas em grafos não ponderados."

Contexto: Uma equipe precisa achar, numa rede de metrô em que todas as conexões entre
estações contam igual, a rota com o menor número de conexões entre duas estações. Ela
decide percorrer a rede a partir da estação de origem com busca em largura.

Comando: Com base na situação descrita, por que a busca em largura atende ao que a
equipe precisa?

A) Encontra o caminho com menor número de arestas quando as conexões têm o mesmo peso.   ← correta
B) Encontra o caminho de menor custo total quando as conexões têm pesos diferentes.
C) Visita cada estação exatamente duas vezes antes de escolher a rota final.
D) Detecta os ciclos da rede antes de visitar a estação de destino.

Fonte: P1, página 12, com o trecho acima.

Autoauditoria:
- O contexto é necessário: sem ele, não se sabe que as conexões têm o mesmo peso.
- (B) é gêmeo malvado: mesma forma, troca "o mesmo peso" por "pesos diferentes".
- Comando em pergunta, alternativas com maiúscula, nenhum termo repetido em todas.
- Nenhuma errada é defensável pelo trecho.
</exemplo_1_questao_adequada>

<exemplo_2_violacao_corrigida>
Comando: Que estrutura a busca em largura usa para guardar os vértices descobertos?

ANTES:
A) Pilha.
B) Fila.   ← correta
C) Recursão.
D) Lista ordenada.

Violação: alternativas de uma ou duas palavras são rótulos. Reconhecer o nome basta, e
nenhum raciocínio é exigido.

DEPOIS:
A) Uma pilha, que devolve primeiro o último vértice guardado.
B) Uma fila, que devolve primeiro o vértice guardado há mais tempo.   ← correta
C) Uma pilha de chamadas recursivas, uma para cada vizinho visitado.
D) Uma lista ordenada pelos rótulos dos vértices.

Agora cada alternativa é uma afirmação completa e simétrica, e (A) é gêmeo malvado:
mesma forma, comportamento trocado.
</exemplo_2_violacao_corrigida>

</exemplos>
