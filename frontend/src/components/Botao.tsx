import type { ButtonHTMLAttributes } from "react";

type Variante = "primario" | "manter" | "descartar" | "fantasma";

interface BotaoProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
}

export function Botao({
  variante = "primario",
  type = "button",
  className = "",
  ...resto
}: BotaoProps) {
  return (
    <button
      type={type}
      className={`botao botao-${variante} ${className}`.trim()}
      {...resto}
    />
  );
}
