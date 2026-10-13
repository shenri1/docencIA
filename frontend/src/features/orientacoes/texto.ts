import type { Orientacao } from "../../api/tipos";

/** O mesmo texto que o modelo recebe no pedido (backend: formatar_orientacoes). */
export function textoOrientacao(o: Pick<Orientacao, "cruzar_com" | "o_que_mudar">): string {
  return [
    o.cruzar_com ? `Articular com: ${o.cruzar_com}` : null,
    o.o_que_mudar ? `Mudar: ${o.o_que_mudar}` : null,
  ]
    .filter(Boolean)
    .join(". ");
}
