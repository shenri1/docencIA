import createClient, { type Middleware } from "openapi-fetch";
import { ErroApi, erroDeResposta } from "./erros";
import type { paths } from "./schema";

interface OpcoesCliente {
  baseUrl: string;
  obterToken: () => string | null;
  /** Chamado quando a API recusa (401) uma requisição que levava token. */
  aoNaoAutorizado: () => void;
}

export function criarCliente({
  baseUrl,
  obterToken,
  aoNaoAutorizado,
}: OpcoesCliente) {
  const cliente = createClient<paths>({ baseUrl });

  const autenticacao: Middleware = {
    onRequest({ request }) {
      const token = obterToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
    onResponse({ request, response }) {
      // 401 sem token (login errado) é resposta normal, não sessão expirada.
      if (response.status === 401 && request.headers.has("Authorization")) {
        aoNaoAutorizado();
      }
      return response;
    },
  };

  cliente.use(autenticacao);
  return cliente;
}

export type ClienteApi = ReturnType<typeof criarCliente>;

interface Resultado<D> {
  data?: D;
  error?: unknown;
  response: Response;
}

/** Devolve o corpo de sucesso ou lança ErroApi (inclusive para falha de rede). */
export async function desembrulhar<D>(pendente: Promise<Resultado<D>>): Promise<D> {
  let resultado: Resultado<D>;
  try {
    resultado = await pendente;
  } catch {
    throw new ErroApi(
      0,
      "Não foi possível falar com o servidor. Verifique sua conexão e tente de novo.",
    );
  }
  if (!resultado.response.ok) {
    throw erroDeResposta(resultado.response.status, resultado.error);
  }
  return resultado.data as D;
}
