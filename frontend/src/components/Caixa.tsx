import { useId, type InputHTMLAttributes } from "react";
import { IconeErro } from "./Icones";

interface CaixaProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  rotulo: string;
  erro?: string | null;
}

export function Caixa({ rotulo, erro, ...input }: CaixaProps) {
  const id = useId();
  const idErro = `${id}-erro`;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-2">
        <input
          id={id}
          type="checkbox"
          className="caixa mt-0.5"
          aria-invalid={erro ? true : undefined}
          aria-describedby={erro ? idErro : undefined}
          {...input}
        />
        <label htmlFor={id} className="font-grotesca text-detalhe text-texto">
          {rotulo}
        </label>
      </div>
      {erro && (
        <p
          id={idErro}
          role="alert"
          className="flex items-start gap-1.5 font-grotesca text-detalhe text-descartar"
        >
          <span className="mt-0.5 shrink-0">
            <IconeErro />
          </span>
          {erro}
        </p>
      )}
    </div>
  );
}
