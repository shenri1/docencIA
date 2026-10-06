import type { MarcoBanco, MarcoSessao } from "../../api/tipos";

/** Uma sessão pode ter mais de um banco; o fluxo segue o mais recente. */
export function bancoMaisRecente(marco: MarcoSessao): MarcoBanco | null {
  return marco.bancos.reduce<MarcoBanco | null>(
    (maisNovo, atual) =>
      maisNovo === null || atual.banco_id > maisNovo.banco_id ? atual : maisNovo,
    null,
  );
}

export type RotaDoMarco =
  | "/sessoes/$sessaoId/materiais"
  | "/sessoes/$sessaoId/geracao"
  | "/sessoes/$sessaoId/banco"
  | "/sessoes/$sessaoId/provas";

/**
 * M1 → materiais; sem banco, ou banco aberto com lacunas →
 * geração; congelado ou com provas → provas; o resto → banco. Só a entrada por
 * /sessoes/:id usa isto, para que "seguir com lacunas" não seja desfeito ao
 * recarregar /banco.
 */
export function rotaDoMarco(marco: MarcoSessao): RotaDoMarco {
  if (marco.marco === "m1_materiais") return "/sessoes/$sessaoId/materiais";
  const banco = bancoMaisRecente(marco);
  if (banco === null || banco.marco === "m1_materiais" || banco.marco === "m2_banco") {
    return "/sessoes/$sessaoId/geracao";
  }
  if (banco.marco === "m3_exclusoes" && banco.lacunas > 0) {
    return "/sessoes/$sessaoId/geracao";
  }
  // `concluido` volta a ter destino próprio (exportações).
  if (banco.marco === "m6_provas" || banco.marco === "m10_docx" || banco.marco === "concluido") {
    return "/sessoes/$sessaoId/provas";
  }
  return "/sessoes/$sessaoId/banco";
}
