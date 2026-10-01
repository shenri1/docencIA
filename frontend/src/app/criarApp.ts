import type { QueryClient } from "@tanstack/react-query";
import type { RouterHistory } from "@tanstack/react-router";
import { criarCliente } from "../api/cliente";
import { lerToken, limparToken } from "../auth/token";
import { criarRouter } from "../routes";

interface Opcoes {
  baseUrl: string;
  queryClient: QueryClient;
  history?: RouterHistory;
}

export function criarApp({ baseUrl, queryClient, history }: Opcoes) {
  // O cliente precisa chamar o roteador no 401 e o roteador precisa do cliente
  // no contexto: a referência só é lida quando o 401 acontece.
  let router!: ReturnType<typeof criarRouter>;

  const cliente = criarCliente({
    baseUrl,
    obterToken: lerToken,
    aoNaoAutorizado: () => {
      const atual = router.state.location;
      limparToken();
      queryClient.clear();
      if (atual.pathname === "/login") return;
      void router.navigate({ to: "/login", search: { redirect: atual.href } });
    },
  });

  router = criarRouter({ queryClient, cliente }, history);
  return { router, queryClient, cliente };
}

export type App = ReturnType<typeof criarApp>;
