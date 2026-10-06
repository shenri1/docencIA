import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { DOCENTE } from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

describe("política de privacidade", () => {
  it("abre sem token e descreve o que o sistema guarda", async () => {
    renderApp("/privacidade");

    expect(
      await screen.findByRole("heading", { level: 1, name: "Política de privacidade" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/hash bcrypt/)).toBeInTheDocument();
    expect(screen.getByText(/pseudônimo HMAC/)).toBeInTheDocument();
    expect(screen.getByText(/a definir pela instituição/)).toBeInTheDocument();
  });

  it("a política abre com token, sem redirecionar", async () => {
    const { router } = renderApp("/privacidade", { token: "t" });

    expect(
      await screen.findByRole("heading", { level: 1, name: "Política de privacidade" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/privacidade");
  });

  it("o cadastro tem o link para a política, em nova aba", async () => {
    renderApp("/cadastro");

    const link = await screen.findByRole("link", { name: "Ler a política de privacidade" });
    expect(link).toHaveAttribute("href", "/privacidade");
    expect(link).toHaveAttribute("target", "_blank");
  });
});

describe("landing", () => {
  it("sem token, / mostra a landing", async () => {
    renderApp("/");

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Bancos de questões a partir dos seus materiais, com a fonte de cada questão.",
      }),
    ).toBeInTheDocument();
    const principal = screen.getByRole("main");
    expect(within(principal).getByRole("link", { name: "Criar conta" })).toHaveAttribute(
      "href",
      "/cadastro",
    );
    expect(within(principal).getByRole("link", { name: "Entrar" })).toHaveAttribute(
      "href",
      "/login",
    );
    expect(screen.getByRole("heading", { name: "Como funciona" })).toBeInTheDocument();
    expect(screen.getByText(/insuficiência de fonte/)).toBeInTheDocument();
    expect(screen.getByText("Não é um chat.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Política de privacidade" })).toHaveAttribute(
      "href",
      "/privacidade",
    );
  });

  it("com token, / leva ao painel", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () => HttpResponse.json([])),
    );
    const { router } = renderApp("/", { token: "t" });

    await waitFor(() => expect(router.state.location.pathname).toBe("/sessoes"));
    expect(await screen.findByRole("heading", { name: "Minhas sessões" })).toBeInTheDocument();
  });
});
