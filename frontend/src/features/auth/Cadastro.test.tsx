import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { API, renderApp } from "../../test/renderApp";

async function preencher(
  user: ReturnType<typeof renderApp>["user"],
  { nome = "Ana Souza", credencial = "ana.souza", senha = "segredo123", lgpd = true } = {},
) {
  await user.type(await screen.findByLabelText("Nome completo"), nome);
  await user.type(screen.getByLabelText("Credencial institucional"), credencial);
  await user.type(screen.getByLabelText("Senha"), senha);
  if (lgpd) await user.click(screen.getByRole("checkbox", { name: /LGPD/ }));
}

describe("Cadastro", () => {
  it("envia só os três campos que a API aceita e leva ao login", async () => {
    let corpo: unknown = null;
    server.use(
      http.post(`${API}/auth/registrar`, async ({ request }) => {
        corpo = await request.json();
        return HttpResponse.json(
          { id: 2, nome: "Ana Souza", credencial_institucional: "ana.souza", perfil: "docente" },
          { status: 201 },
        );
      }),
    );
    const { user, router } = renderApp("/cadastro");

    await preencher(user);
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(corpo).toEqual({
      nome: "Ana Souza",
      credencial_institucional: "ana.souza",
      senha: "segredo123",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/conta criada/i);
  });

  it("exige o consentimento LGPD antes de enviar", async () => {
    const { user } = renderApp("/cadastro");

    await preencher(user, { lgpd: false });
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    expect(
      await screen.findByText("Aceite o tratamento de dados para criar a conta."),
    ).toBeInTheDocument();
  });

  it("recusa senha curta sem chamar a API", async () => {
    const { user } = renderApp("/cadastro");

    await preencher(user, { senha: "curta" });
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    expect(await screen.findByText(/pelo menos 8/)).toBeInTheDocument();
  });

  it("conta bytes: 40 letras acentuadas passam de 72 bytes", async () => {
    const { user } = renderApp("/cadastro");

    await preencher(user, { senha: "ç".repeat(40) });
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/72 bytes/);
  });

  it("mostra a recusa de credencial já cadastrada", async () => {
    server.use(
      http.post(`${API}/auth/registrar`, () =>
        HttpResponse.json(
          {
            detail: "Credencial institucional 'ana.souza' já cadastrada.",
            codigo: "CREDENCIAL_JA_CADASTRADA",
          },
          { status: 409 },
        ),
      ),
    );
    const { user, router } = renderApp("/cadastro");

    await preencher(user);
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/já cadastrada/);
    expect(router.state.location.pathname).toBe("/cadastro");
  });

  it("leva o 422 da API para o campo certo", async () => {
    server.use(
      http.post(`${API}/auth/registrar`, () =>
        HttpResponse.json(
          {
            detail: [
              {
                loc: ["body", "credencial_institucional"],
                msg: "String should have at most 255 characters",
                type: "string_too_long",
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );
    const { user } = renderApp("/cadastro");

    await preencher(user);
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    const campo = await screen.findByLabelText("Credencial institucional");
    await waitFor(() => expect(campo).toHaveAccessibleDescription(/at most 255/));
  });
});
