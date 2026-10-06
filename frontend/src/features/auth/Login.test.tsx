import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { lerToken } from "../../auth/token";
import { API, renderApp } from "../../test/renderApp";
import { destinoSeguro } from "./destinoSeguro";

const DOCENTE = {
  id: 1,
  nome: "Ana Souza",
  credencial_institucional: "ana.souza",
  perfil: "docente",
};

function backendComLoginValido(corpos: string[] = [], tipos: string[] = []) {
  server.use(
    http.post(`${API}/auth/login`, async ({ request }) => {
      tipos.push(request.headers.get("content-type") ?? "");
      corpos.push(await request.text());
      return HttpResponse.json({ access_token: "jwt-123", token_type: "bearer" });
    }),
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes`, () => HttpResponse.json([])),
  );
}

describe("Login", () => {
  it("envia credencial e senha como formulário e vai ao painel", async () => {
    const corpos: string[] = [];
    const tipos: string[] = [];
    backendComLoginValido(corpos, tipos);
    const { user, router } = renderApp("/login");

    await user.type(
      await screen.findByLabelText("Credencial institucional"),
      "ana.souza",
    );
    await user.type(screen.getByLabelText("Senha"), "segredo123");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/sessoes"));
    const enviado = new URLSearchParams(corpos[0]);
    expect(enviado.get("username")).toBe("ana.souza");
    expect(enviado.get("password")).toBe("segredo123");
    expect(tipos[0]).toMatch(/^application\/x-www-form-urlencoded/);
    expect(lerToken()).toBe("jwt-123");
  });

  it("volta ao destino de origem depois de entrar", async () => {
    backendComLoginValido();
    const { user, router } = renderApp("/login?redirect=%2Fsessoes%2Fnova");

    await user.type(await screen.findByLabelText("Credencial institucional"), "a");
    await user.type(screen.getByLabelText("Senha"), "segredo123");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/nova"),
    );
  });

  it("mostra a recusa da API e não guarda token", async () => {
    server.use(
      http.post(`${API}/auth/login`, () =>
        HttpResponse.json(
          { detail: "Credenciais inválidas.", codigo: "CREDENCIAIS_INVALIDAS" },
          { status: 401 },
        ),
      ),
    );
    const { user, router } = renderApp("/login");

    await user.type(await screen.findByLabelText("Credencial institucional"), "x");
    await user.type(screen.getByLabelText("Senha"), "errada123");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Credenciais inválidas.",
    );
    expect(lerToken()).toBeNull();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("pede os campos vazios sem chamar a API", async () => {
    const { user } = renderApp("/login");

    await user.click(await screen.findByRole("button", { name: "Entrar" }));

    expect(
      await screen.findByText("Informe sua credencial institucional."),
    ).toBeInTheDocument();
    expect(screen.getByText("Informe sua senha.")).toBeInTheDocument();
  });

  it("quem já tem token vai direto ao painel", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () => HttpResponse.json([])),
    );
    const { router } = renderApp("/login", { token: "ja-logado" });

    await waitFor(() => expect(router.state.location.pathname).toBe("/sessoes"));
  });

  it("avisa que a conta foi criada quando vem do cadastro", async () => {
    renderApp("/login?criada=1");

    expect(await screen.findByRole("status")).toHaveTextContent(/conta criada/i);
  });

  it("orienta quem esqueceu a senha, sem prometer recuperação por e-mail", async () => {
    renderApp("/login");

    expect(await screen.findByText(/administrador do sistema/i)).toBeInTheDocument();
  });
});

describe("destinoSeguro", () => {
  it("aceita caminho interno, com query", () => {
    expect(destinoSeguro("/sessoes/5?x=1")).toBe("/sessoes/5?x=1");
  });

  it.each([undefined, "", "https://evil.test", "//evil.test", "/\\evil.test", "sessoes"])(
    "recusa %j e cai no painel",
    (valor) => {
      expect(destinoSeguro(valor)).toBe("/sessoes");
    },
  );
});
