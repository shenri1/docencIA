import type { ReactNode } from "react";
import { IconeAviso, IconeErro, IconeInfo, IconeOk } from "./Icones";

type Variante = "erro" | "aviso" | "info" | "sucesso";

const ESTILO: Record<Variante, string> = {
  erro: "bg-descartar-fundo border-descartar text-descartar",
  aviso: "bg-aviso-fundo border-aviso text-aviso",
  info: "bg-cartao border-borda text-texto",
  sucesso: "bg-manter-fundo border-manter text-manter",
};

const ICONE: Record<Variante, () => ReactNode> = {
  erro: IconeErro,
  aviso: IconeAviso,
  info: IconeInfo,
  sucesso: IconeOk,
};

interface AlertaProps {
  variante?: Variante;
  titulo?: string;
  children?: ReactNode;
}

export function Alerta({ variante = "info", titulo, children }: AlertaProps) {
  const Icone = ICONE[variante];
  return (
    <div
      role={variante === "erro" ? "alert" : "status"}
      className={`flex gap-3 rounded border px-4 py-3 font-grotesca text-detalhe ${ESTILO[variante]}`}
    >
      <span className="mt-0.5 shrink-0">
        <Icone />
      </span>
      <div className="min-w-0">
        {titulo && <p className="font-semibold">{titulo}</p>}
        {children && <div className={titulo ? "mt-1" : undefined}>{children}</div>}
      </div>
    </div>
  );
}
