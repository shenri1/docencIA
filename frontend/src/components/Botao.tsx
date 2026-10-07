import { useEffect, useRef, type ButtonHTMLAttributes, type MouseEvent } from "react";

type Variante = "primario" | "manter" | "descartar" | "fantasma";

interface BotaoProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
}

// O `disabled` vindo de `isPending` chega um tick depois do clique (o TanStack
// Query notifica por setTimeout), e um duplo clique cabe nessa janela. Esta
// trava é síncrona: handler assíncrono segura até resolver; os demais, até o
// próximo render (que traz o `disabled` ou troca a tela) ou 400 ms.
const JANELA_DUPLO_CLIQUE_MS = 400;

export function Botao({
  variante = "primario",
  type = "button",
  className = "",
  onClick,
  ...resto
}: BotaoProps) {
  const travado = useRef(false);
  const emVoo = useRef(false);

  useEffect(() => {
    if (!emVoo.current) travado.current = false;
  });

  function aoClicar(evento: MouseEvent<HTMLButtonElement>) {
    if (travado.current) return evento.preventDefault();
    travado.current = true;
    const liberar = () => {
      emVoo.current = false;
      travado.current = false;
    };
    try {
      const retorno: unknown = onClick?.(evento);
      if (retorno instanceof Promise) {
        emVoo.current = true;
        void retorno.finally(liberar);
      } else {
        setTimeout(liberar, JANELA_DUPLO_CLIQUE_MS);
      }
    } catch (erro) {
      liberar();
      throw erro;
    }
  }

  return (
    <button
      type={type}
      className={`botao botao-${variante} ${className}`.trim()}
      onClick={aoClicar}
      {...resto}
    />
  );
}
