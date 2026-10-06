import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { lerToken } from "./auth/token";
import { server } from "./mocks/server";
import { DOCENTE } from "./test/fixtures";
import { API, renderApp } from "./test/renderApp";

describe("rotas protegidas", () => {
  it("sem token, vai ao login levando o destino", async () => {
    const { router } = renderApp("/sessoes/nova");

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(router.state.location.search).toMatchObject({
      redirect: "/sessoes/nova",
    });
  });

  it("401 em qualquer rota limpa o token e volta ao login com o destino", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () =>
        HttpResponse.json(
          { detail: "Token inválido ou expirado.", codigo: "TOKEN_INVALIDO" },
          { status: 401 },
        ),
      ),
    );
    const { router } = renderApp("/sessoes", { token: "expirado" });

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(router.state.location.search).toMatchObject({ redirect: "/sessoes" });
    expect(lerToken()).toBeNull();
    expect(screen.queryByText("Ana Souza")).not.toBeInTheDocument();
  });
});

describe("casca autenticada", () => {
  it("mostra o nome do docente e sai limpando o token", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () => HttpResponse.json([])),
    );
    const { user, router } = renderApp("/sessoes", { token: "valido" });

    expect(await screen.findByText("Ana Souza")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Sair" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(lerToken()).toBeNull();
  });
});
