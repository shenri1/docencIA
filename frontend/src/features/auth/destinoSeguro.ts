const PAINEL = "/sessoes";

/**
 * O parâmetro `redirect` vem da URL e portanto de fora: só caminho interno é
 * aceito, senão o login viraria um redirecionador aberto (`//outro.site`).
 */
export function destinoSeguro(redirect: string | undefined): string {
  if (!redirect) return PAINEL;
  if (!redirect.startsWith("/")) return PAINEL;
  if (redirect.startsWith("//") || redirect.startsWith("/\\")) return PAINEL;
  return redirect;
}
