<exemplo_afirmativas>
Trechos: (P1, página 12) "A busca em largura visita os vértices por camadas de
distância crescente a partir da origem." (P1, página 13) "A busca em largura mantém os
vértices descobertos numa fila."

Configuração pedida: I e II verdadeiras, III falsa.

Contexto: Um sistema de recomendação percorre a rede de amizades de um usuário com busca
em largura para sugerir primeiro as pessoas mais próximas dele.
Comando: A partir da situação descrita, avalie as afirmações a seguir.
I. (verdadeira) As pessoas a uma amizade de distância são visitadas antes das que estão
   a duas. Justificativa: a visita é por camadas de distância crescente (página 12).
II. (verdadeira) Os perfis descobertos e ainda não visitados esperam numa fila.
   Justificativa: a busca mantém os descobertos numa fila (página 13).
III. (falsa) O perfil descoberto por último é o próximo a ser visitado.
   Justificativa: com fila, o próximo é o descoberto há mais tempo (página 13).

Por que é adequada: as três tratam do mesmo conteúdo (a ordem de visita da busca em
largura), cada uma se verifica num trecho, e a falsa erra por um comportamento
plausível, o da pilha.
</exemplo_afirmativas>
