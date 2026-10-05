import type { components } from "../api/schema";

type Formato = components["schemas"]["FormatoArquivo"];

const decimal = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const duasCasas = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** A API manda o percentual como texto decimal ("25.00"); a tela mostra "25,00". */
export function formatarPercentual(valor: string): string {
  return duasCasas.format(Number(valor));
}

export function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${decimal.format(bytes / 1024)} KB`;
  return `${decimal.format(bytes / 1024 ** 2)} MB`;
}

// Páginas lógicas: slides no pptx, páginas no resto. txt não tem contagem.
export function rotuloDePaginas(contagem: number | null | undefined, formato: Formato): string | null {
  if (contagem == null) return null;
  const [um, varios] = formato === "pptx" ? ["slide", "slides"] : ["página", "páginas"];
  return `${contagem} ${contagem === 1 ? um : varios}`;
}
