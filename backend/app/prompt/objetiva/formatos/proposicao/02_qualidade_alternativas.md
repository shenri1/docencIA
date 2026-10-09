<qualidade_alternativas>

<regra_1_anti_correta_gigante>
Nenhuma alternativa pode exceder 1,5× a média de palavras das demais alternativas, e a
correta não pode ser mais que 20% mais longa que a errada mais longa.

VIOLAÇÃO:
A) Visita os vértices por camadas de distância. (7 palavras)
B) Explora cada ramo até o fim antes de voltar. (9 palavras)
C) Visita primeiro todos os vizinhos de um vértice antes de avançar para os vizinhos
   dos vizinhos, o que garante encontrar o caminho com menor número de arestas em
   grafos não ponderados. (31 palavras) ← VIOLA
D) Escolhe o próximo vértice ao acaso a cada passo. (9 palavras)

CORREÇÃO:
C) Garante o caminho com menos arestas em grafos não ponderados. (10 palavras)

Razão: alternativa correta visivelmente mais longa é entregue de graça a quem não
estudou.
</regra_1_anti_correta_gigante>

<regra_2_simetria_linguistica>
Todas as alternativas compartilham o mesmo registro. Só a correta usar conectivos
elaborados, ressalvas ou absolutos ("sempre", "nunca") entrega a resposta pela forma.

Comando: Para guardar os vértices descobertos, a busca em largura usa

VIOLAÇÃO:
A) uma pilha, que devolve primeiro o último vértice guardado.
B) uma lista ordenada pelos rótulos dos vértices.
C) uma fila, estrutura que garante o processamento na ordem de chegada e é justamente
   o que caracteriza esse percurso. ← VIOLA
D) uma tabela de dispersão indexada pelos vértices.

CORREÇÃO:
C) uma fila, que devolve primeiro o vértice guardado há mais tempo.
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
assintótica. Bons distratores vêm de erros comuns de quem estuda o conteúdo ou de
soluções erradas, mas plausíveis, para o problema do comando.
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

<regra_7_sem_alternativa_generica>
Nunca use "todas as anteriores", "nenhuma das anteriores", "todas estão corretas" ou
equivalentes. Além de entregar a resposta por eliminação, o sistema reordena as
alternativas em cada versão da prova, e "anteriores" passa a indicar outras.
</regra_7_sem_alternativa_generica>

<regra_8_sem_par_excludente>
Duas alternativas que se negam ("aumenta" e "não aumenta") dizem que a correta é uma
das duas, e o chute fica fácil. Cada errada é errada por um motivo próprio.
</regra_8_sem_par_excludente>

<regra_9_termo_comum_no_comando>
Se todas as alternativas começam com o mesmo verbo ou substantivo, ele vai para o
comando. Repetir cansa a leitura e não acrescenta nada.
</regra_9_termo_comum_no_comando>

<regra_10_pontuacao_do_comando>
- Comando em pergunta termina com "?", e cada alternativa começa com maiúscula e
  responde à pergunta.
- Comando em frase incompleta não tem pontuação final, e cada alternativa começa com
  minúscula e completa a frase.
</regra_10_pontuacao_do_comando>

</qualidade_alternativas>
