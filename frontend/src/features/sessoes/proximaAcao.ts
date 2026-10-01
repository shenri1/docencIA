import type { Marco, MarcoSessao } from "../../api/tipos";

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

  // Uma sessão pode ter mais de um banco; o painel mostra o mais recente.
  const ultimo = marco.bancos.reduce<MarcoSessao["bancos"][number] | null>(
    (maisNovo, atual) =>
      maisNovo === null || atual.banco_id > maisNovo.banco_id ? atual : maisNovo,
    null,
  );
  if (ultimo === null) return "Gerar banco";
  if (ultimo.marco === "m1_materiais" || ultimo.marco === "m2_banco") {
    return "Gerar banco";
  }
  return ROTULO_DO_BANCO[ultimo.marco];
}
