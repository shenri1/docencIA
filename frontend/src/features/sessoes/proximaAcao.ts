import type { Marco, MarcoSessao } from "../../api/tipos";
import { bancoMaisRecente } from "./marco";

const ROTULO_DO_BANCO: Record<Exclude<Marco, "m1_materiais" | "m2_banco">, string> = {
  m3_exclusoes: "Revisar banco",
  m6_provas: "Montar provas",
  m10_docx: "Exportar provas",
  concluido: "Ver exportações",
  bloqueado: "Ver pendência",
};

/** Próximo passo em linguagem do docente, derivado só do marco que a API informa. */
export function proximaAcao(marco: MarcoSessao): string {
  if (marco.marco === "m1_materiais") return "Enviar materiais";

  const ultimo = bancoMaisRecente(marco);
  if (ultimo === null) return "Gerar banco";
  if (ultimo.marco === "m1_materiais" || ultimo.marco === "m2_banco") {
    return "Gerar banco";
  }
  if (ultimo.marco === "m3_exclusoes" && ultimo.lacunas > 0) {
    return "Continuar geração";
  }
  return ROTULO_DO_BANCO[ultimo.marco];
}
