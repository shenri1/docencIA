// Espelha o schema do cadastro: mínimo de 8 caracteres e teto de 72 bytes
// em UTF-8 (bcrypt). Conveniência — a API continua sendo a autoridade.
export function mensagemDeSenha(senha: string): string | null {
  if (senha.length < 8) return "A senha precisa ter pelo menos 8 caracteres.";
  if (new TextEncoder().encode(senha).length > 72) {
    return "A senha passa de 72 bytes. Letras acentuadas ocupam mais de 1 byte; use uma senha mais curta.";
  }
  return null;
}

export function somaDosPercentuais(pF: number, pM: number, pD: number): number {
  return pF + pM + pD;
}

/** Inteiro dentro da faixa, ou null para campo vazio ou fora dela. */
export function inteiroEntre(texto: string, min: number, max: number): number | null {
  if (texto.trim() === "") return null;
  const n = Number(texto);
  return Number.isInteger(n) && n >= min && n <= max ? n : null;
}
