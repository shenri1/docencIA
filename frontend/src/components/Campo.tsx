import { useId, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { IconeErro } from "./Icones";

interface BaseProps {
  rotulo: string;
  erro?: string | null;
  ajuda?: string;
}

function Mensagens({
  idAjuda,
  idErro,
  ajuda,
  erro,
}: {
  idAjuda: string;
  idErro: string;
  ajuda?: string;
  erro?: string | null;
}) {
  return (
    <>
      {ajuda && (
        <p id={idAjuda} className="font-grotesca text-detalhe text-texto-suave">
          {ajuda}
        </p>
      )}
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
    </>
  );
}

function descritoPor(ajuda: string | undefined, erro: string | null | undefined, idAjuda: string, idErro: string) {
  return [ajuda ? idAjuda : null, erro ? idErro : null].filter(Boolean).join(" ") || undefined;
}

export function Campo({
  rotulo,
  erro,
  ajuda,
  className = "",
  ...input
}: BaseProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const idAjuda = `${id}-ajuda`;
  const idErro = `${id}-erro`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-grotesca text-rotulo-lg text-texto">
        {rotulo}
      </label>
      <input
        id={id}
        className={`campo ${className}`.trim()}
        aria-invalid={erro ? true : undefined}
        aria-describedby={descritoPor(ajuda, erro, idAjuda, idErro)}
        {...input}
      />
      <Mensagens idAjuda={idAjuda} idErro={idErro} ajuda={ajuda} erro={erro} />
    </div>
  );
}

export function CampoSelecao({
  rotulo,
  erro,
  ajuda,
  className = "",
  children,
  ...select
}: BaseProps & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId();
  const idAjuda = `${id}-ajuda`;
  const idErro = `${id}-erro`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="font-grotesca text-rotulo-lg text-texto">
        {rotulo}
      </label>
      <select
        id={id}
        className={`campo ${className}`.trim()}
        aria-invalid={erro ? true : undefined}
        aria-describedby={descritoPor(ajuda, erro, idAjuda, idErro)}
        {...select}
      >
        {children}
      </select>
      <Mensagens idAjuda={idAjuda} idErro={idErro} ajuda={ajuda} erro={erro} />
    </div>
  );
}
