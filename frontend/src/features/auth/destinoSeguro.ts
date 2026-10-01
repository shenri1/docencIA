/**
 * O parâmetro `redirect` vem da URL e portanto de fora: só caminho interno é
 * aceito, senão o login viraria um redirecionador aberto (`//outro.site`).
 */
export function destinoSeguro(redirect: string | undefined): string {
  if (!redirect) return "/";
  if (!redirect.startsWith("/")) return "/";
  if (redirect.startsWith("//") || redirect.startsWith("/\\")) return "/";
  return redirect;
}
