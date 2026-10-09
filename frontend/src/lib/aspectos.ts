/** Aspectos da discursiva com itens, na ordem em que chegam. */
export function agruparPorItem<T extends { item?: number | null }>(
  aspectos: T[],
): { item: number | null; aspectos: T[] }[] {
  const grupos: { item: number | null; aspectos: T[] }[] = [];
  for (const aspecto of aspectos) {
    const item = aspecto.item ?? null;
    const ultimo = grupos.at(-1);
    if (ultimo && ultimo.item === item) ultimo.aspectos.push(aspecto);
    else grupos.push({ item, aspectos: [aspecto] });
  }
  return grupos;
}

export const letraDoItem = (item: number): string => "abc"[item - 1] ?? String(item);
