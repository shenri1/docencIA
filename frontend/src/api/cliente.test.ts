import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { ErroApi } from "./erros";
import { criarCliente, desembrulhar } from "./cliente";

const BASE = "http://api.test";

function clienteCom(token: string | null, aoNaoAutorizado = vi.fn()) {
  return {
    aoNaoAutorizado,
    cliente: criarCliente({
      baseUrl: BASE,
      obterToken: () => token,
      aoNaoAutorizado,
    }),
  };
}

describe("cliente da API", () => {
  it("envia o token como Bearer", async () => {
    let cabecalho: string | null = null;
    server.use(
      http.get(`${BASE}/auth/me`, ({ request }) => {
        cabecalho = request.headers.get("authorization");
        return HttpResponse.json({
          id: 1,
          nome: "Ana",
          credencial_institucional: "ana",
          perfil: "docente",
        });
      }),
    );
    const { cliente } = clienteCom("tok123");

    const docente = await desembrulhar(cliente.GET("/auth/me"));

    expect(cabecalho).toBe("Bearer tok123");
    expect(docente.nome).toBe("Ana");
  });

  it("não envia Authorization quando não há token", async () => {
    let cabecalho: string | null = "x";
    server.use(
      http.get(`${BASE}/sessoes`, ({ request }) => {
        cabecalho = request.headers.get("authorization");
        return HttpResponse.json([]);
      }),
    );
    const { cliente } = clienteCom(null);

    await cliente.GET("/sessoes");

    expect(cabecalho).toBeNull();
  });

  it("avisa quando um 401 chega com token enviado", async () => {
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json(
          { detail: "Token inválido ou expirado.", codigo: "TOKEN_INVALIDO" },
          { status: 401 },
        ),
      ),
    );
    const { cliente, aoNaoAutorizado } = clienteCom("velho");

    await expect(desembrulhar(cliente.GET("/auth/me"))).rejects.toMatchObject({
      status: 401,
      codigo: "TOKEN_INVALIDO",
    });
    expect(aoNaoAutorizado).toHaveBeenCalledTimes(1);
  });

  it("não trata como sessão expirada o 401 de um login sem token", async () => {
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json(
          { detail: "Credenciais inválidas.", codigo: "CREDENCIAIS_INVALIDAS" },
          { status: 401 },
        ),
      ),
    );
    const { cliente, aoNaoAutorizado } = clienteCom(null);

    await expect(desembrulhar(cliente.GET("/auth/me"))).rejects.toBeInstanceOf(
      ErroApi,
    );
    expect(aoNaoAutorizado).not.toHaveBeenCalled();
  });

  it("transforma falha de rede em ErroApi de status 0", async () => {
    server.use(http.get(`${BASE}/sessoes`, () => HttpResponse.error()));
    const { cliente } = clienteCom("t");

    await expect(desembrulhar(cliente.GET("/sessoes"))).rejects.toMatchObject({
      status: 0,
      message: expect.stringMatching(/servidor/i),
    });
  });
});
