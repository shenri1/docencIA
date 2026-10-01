// sessionStorage: sobrevive a recarregar a página e some ao fechar a aba. Não há
// refresh token, então token expirado só se resolve entrando de novo.
const CHAVE = "docencia.token";

// O acesso à storage pode lançar (janela privada, dados do site bloqueados); sem
// token o app apenas pede login, então a falha é engolida de propósito.
export function lerToken(): string | null {
  try {
    return sessionStorage.getItem(CHAVE);
  } catch {
    return null;
  }
}

export function guardarToken(token: string): void {
  try {
    sessionStorage.setItem(CHAVE, token);
  } catch {
    // sem storage o login vale só enquanto a página não recarrega
  }
}

export function limparToken(): void {
  try {
    sessionStorage.removeItem(CHAVE);
  } catch {
    // nada a limpar
  }
}
