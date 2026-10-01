import { QueryClient } from "@tanstack/react-query";
import { createMemoryHistory } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppRaiz } from "../app/AppRaiz";
import { criarApp } from "../app/criarApp";
import { guardarToken } from "../auth/token";

export const API = "http://api.test";

interface Opcoes {
  /** Simula docente já autenticado. */
  token?: string;
}

export function renderApp(rota: string, { token }: Opcoes = {}) {
  if (token) guardarToken(token);
  const app = criarApp({
    baseUrl: API,
    history: createMemoryHistory({ initialEntries: [rota] }),
    queryClient: new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    }),
  });
  render(<AppRaiz app={app} />);
  return { ...app, user: userEvent.setup() };
}
