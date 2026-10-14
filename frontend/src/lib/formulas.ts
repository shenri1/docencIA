// Mesma regra de backend/app/services/notacao.py:separar. Os dois leem
// src/test/fixtures/notacao.json; mudar um exige mudar o outro.
export type Segmento =
  | { tipo: "texto"; conteudo: string }
  | { tipo: "formula"; latex: string; destaque: boolean };

const FORMULA = /\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]/g;

export function separar(texto: string): Segmento[] {
  const segmentos: Segmento[] = [];
  let posicao = 0;
  for (const achado of texto.matchAll(FORMULA)) {
    const inicio = achado.index ?? 0;
    if (inicio > posicao) segmentos.push({ tipo: "texto", conteudo: texto.slice(posicao, inicio) });
    segmentos.push({
      tipo: "formula",
      latex: achado[1] ?? achado[2] ?? "",
      destaque: achado[1] === undefined,
    });
    posicao = inicio + achado[0].length;
  }
  if (posicao < texto.length) segmentos.push({ tipo: "texto", conteudo: texto.slice(posicao) });
  return segmentos;
}
