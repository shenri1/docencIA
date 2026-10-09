import type { ReactNode } from "react";
import { agruparPorItem, letraDoItem } from "../../lib/aspectos";

interface Aspecto {
  ordem: number;
  texto: string;
  item?: number | null;
}

/** Aspectos esperados, agrupados por item quando a discursiva tem itens. */
export function ListaAspectos<T extends Aspecto>({
  aspectos,
  fonte,
}: {
  aspectos: T[];
  fonte: (aspecto: T) => ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3">
      {agruparPorItem(aspectos).map((grupo) => (
        <div key={grupo.item ?? 0} className="flex flex-col gap-2">
          {grupo.item !== null && (
            <h4 className="font-grotesca text-detalhe font-semibold">
              Item {letraDoItem(grupo.item)})
            </h4>
          )}
          <ol className="flex flex-col gap-3">
            {grupo.aspectos.map((aspecto) => (
              <li key={aspecto.ordem} className="flex flex-col gap-1">
                <span className="font-serifa">
                  {aspecto.ordem}. {aspecto.texto}
                </span>
                {fonte(aspecto)}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}
