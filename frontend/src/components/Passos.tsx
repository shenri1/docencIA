interface PassosProps {
  passos: string[];
  /** Posição do passo atual, começando em 1. */
  atual: number;
}

export function Passos({ passos, atual }: PassosProps) {
  return (
    <ol
      aria-label="Etapas da nova sessão"
      className="flex flex-wrap gap-x-6 gap-y-2 font-grotesca text-detalhe"
    >
      {passos.map((nome, i) => {
        const numero = i + 1;
        const estado =
          numero < atual ? "concluido" : numero === atual ? "atual" : "pendente";
        return (
          <li
            key={nome}
            aria-current={estado === "atual" ? "step" : undefined}
            className={
              estado === "atual"
                ? "font-semibold text-texto"
                : "text-texto-suave"
            }
          >
            <span className="tabular mr-1.5">{numero}.</span>
            {nome}
            {estado === "concluido" && <span className="sr-only"> (concluído)</span>}
          </li>
        );
      })}
    </ol>
  );
}

export const PASSOS_NOVA_SESSAO = ["Parâmetros", "Materiais", "Índice"];
