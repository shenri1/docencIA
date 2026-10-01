import type { SVGProps } from "react";

// Ícones de estado: o sistema nunca comunica estado só por cor.
function Base(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    />
  );
}

export const IconeErro = () => (
  <Base>
    <circle cx="8" cy="8" r="6.25" />
    <path d="M8 4.75v3.75M8 10.9v.1" />
  </Base>
);

export const IconeAviso = () => (
  <Base>
    <path d="M8 2.5 14 13H2L8 2.5Z" />
    <path d="M8 6.5v3M8 11.4v.1" />
  </Base>
);

export const IconeOk = () => (
  <Base>
    <circle cx="8" cy="8" r="6.25" />
    <path d="m5.25 8.25 1.9 1.9 3.6-4" />
  </Base>
);

export const IconeInfo = () => (
  <Base>
    <circle cx="8" cy="8" r="6.25" />
    <path d="M8 7.25v3.75M8 5v.1" />
  </Base>
);
