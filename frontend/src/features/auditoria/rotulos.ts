import type { RiscoAuditoria } from "../../api/tipos";

/** o risco em linguagem do docente, não o identificador do enum. */
export const ROTULO_RISCO: Record<RiscoAuditoria, string> = {
  correta_nao_unica: "Mais de uma alternativa pode estar correta",
  distrator_indefensavel: "Alternativa errada fácil de eliminar",
  assimetria_forma: "Alternativa destoa em forma ou tamanho",
};
