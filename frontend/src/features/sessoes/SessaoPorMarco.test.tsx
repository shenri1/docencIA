import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import {
  DOCENTE,
  umBanco,
  umMarcoBanco,
  umMarcoSessao,
  umaSessao,
} from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

function backend(marco: ReturnType<typeof umMarcoSessao>) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes/5`, () => HttpResponse.json(umaSessao({ id: 5 }))),
    http.get(`${API}/sessoes/5/marco`, () => HttpResponse.json(marco)),
    // O umMarcoBanco padrão aponta para o banco 1, e a mesa agora o lê.
    http.get(`${API}/bancos/1`, () => HttpResponse.json(umBanco())),
  );
}

describe("/sessoes/:id lê o marco e redireciona", () => {
  it("M1 leva aos materiais", async () => {
    backend(umMarcoSessao({ sessao_id: 5, marco: "m1_materiais" }));
    server.use(http.get(`${API}/sessoes/5/materiais/indice`, () =>
      HttpResponse.json({ materiais: [], confirmado: false })));
    const { router } = renderApp("/sessoes/5", { token: "t" });

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/materiais"),
    );
  });

  it("M2 sem banco leva à geração", async () => {
    backend(umMarcoSessao({ sessao_id: 5, marco: "m2_banco", n_materiais: 3 }));
    const { router } = renderApp("/sessoes/5", { token: "t" });

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/geracao"),
    );
    expect(
      await screen.findByRole("heading", { name: "Geração do banco" }),
    ).toBeInTheDocument();
  });

  it("banco aberto com lacunas leva à geração", async () => {
    backend(
      umMarcoSessao({
        sessao_id: 5,
        marco: "m2_banco",
        bancos: [umMarcoBanco({ marco: "m3_exclusoes", lacunas: 2 })],
      }),
    );
    const { router } = renderApp("/sessoes/5", { token: "t" });

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/geracao"),
    );
  });

  it("banco completo leva ao banco", async () => {
    backend(
      umMarcoSessao({
        sessao_id: 5,
        marco: "m2_banco",
        bancos: [umMarcoBanco({ marco: "m3_exclusoes", lacunas: 0 })],
      }),
    );
    const { router } = renderApp("/sessoes/5", { token: "t" });

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/banco"),
    );
    expect(
      await screen.findByRole("heading", { name: "Banco de questões" }),
    ).toBeInTheDocument();
  });

  it("recarregar em /banco com lacunas fica em /banco", async () => {
    backend(
      umMarcoSessao({
        sessao_id: 5,
        marco: "m2_banco",
        bancos: [umMarcoBanco({ marco: "m3_exclusoes", lacunas: 2 })],
      }),
    );
    const { router } = renderApp("/sessoes/5/banco", { token: "t" });

    expect(
      await screen.findByRole("heading", { name: "Banco de questões" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/sessoes/5/banco");
  });

  it("mostra a mensagem da API quando a sessão não existe", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes/5/marco`, () =>
        HttpResponse.json(
          { detail: "Sessão 5 não encontrada.", codigo: "SESSAO_NAO_ENCONTRADA" },
          { status: 404 },
        ),
      ),
    );
    const { router } = renderApp("/sessoes/5", { token: "t" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sessão 5 não encontrada.",
    );
    expect(router.state.location.pathname).toBe("/sessoes/5");
  });
});
