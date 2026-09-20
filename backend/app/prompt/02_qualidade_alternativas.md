<qualidade_alternativas>

<regra_1_anti_correta_gigante>
Nenhuma alternativa pode exceder 1,5× a média de palavras do conjunto, e a correta não
pode ser mais que 20% mais longa que a errada mais longa.

VIOLAÇÃO:
A) Percorre o grafo por níveis. (5 palavras)
B) Percorre o grafo em profundidade. (5 palavras)
C) Percorre o grafo visitando primeiro todos os vizinhos de um vértice antes de avançar
   para os vizinhos dos vizinhos, o que garante encontrar o caminho com menor número de
   arestas em grafos não ponderados. (36 palavras) ← VIOLA
D) Percorre o grafo aleatoriamente. (4 palavras)

CORREÇÃO:
C) Percorre o grafo por camadas de distância. (7 palavras)

Razão: alternativa correta visivelmente mais longa é entregue de graça a quem não
estudou.
</regra_1_anti_correta_gigante>

<regra_2_simetria_linguistica>
Todas as alternativas compartilham o mesmo registro. Só a correta usar conectivos
elaborados, ressalvas ou absolutos ("sempre", "nunca") entrega a resposta pela forma.

VIOLAÇÃO:
A) Pilha.
B) Fila.
C) Fila, estrutura que garante o processamento na ordem de chegada e é justamente o que
   caracteriza esse percurso. ← VIOLA
D) Lista ligada.

CORREÇÃO:
C) Fila.
</regra_2_simetria_linguistica>

<regra_3_gemeo_malvado>
Se {{k_alternativas}} for 5 ou menos: pelo menos uma errada deve ser estruturalmente
similar à correta. Se for 6 ou mais: pelo menos duas.

O gêmeo malvado repete a forma da correta e troca um elemento verificável:
  Correta:       Percurso em largura usa fila.
  Gêmeo malvado: Percurso em profundidade usa fila.

Razão: sem gêmeo, a correta se destaca por ser a única que "parece uma resposta".
</regra_3_gemeo_malvado>

<regra_4_plausibilidade>
Erradas devem ser plausíveis à primeira leitura e claramente incorretas para quem domina
o conteúdo. Evite erradas absurdas e evite erradas de outra categoria — se três
alternativas falam de estrutura de dados, a quarta não pode falar de complexidade
assintótica.
</regra_4_plausibilidade>

<regra_5_autoauditoria_unicidade>
Antes de finalizar cada questão, pergunte-se: "alguma errada pode ser defendida com base
no trecho fornecido?" Se sim, a questão é inválida — reescreva-a ou declare insuficiência
de fonte. Unicidade da resposta não é preferência, é condição.
</regra_5_autoauditoria_unicidade>

<regra_6_comando_claro>
Prefira comandos operacionais: "MAIS adequado", "principal", "MAIS provável", "melhor
descreve". Evite "correto" e "incorreto" isolados, e evite absolutos, salvo quando o
próprio trecho os sustenta.

Razão: comando absoluto convida à contestação ("depende"). Comando comparativo é
resistente a recurso por natureza.
</regra_6_comando_claro>

</qualidade_alternativas>
