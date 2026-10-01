import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import {
  DOCENTE,
  umMarcoBanco,
  umMarcoSessao,
  umaSessao,
} from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

function backend({
  sessoes,
  marcos = {},
}: {
  sessoes: ReturnType<typeof umaSessao>[];
  marcos?: Record<number, ReturnType<typeof umMarcoSessao>>;
}) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes`, () => HttpResponse.json(sessoes)),
    http.get(`${API}/sessoes/:id/marco`, ({ params }) => {
      const id = Number(params.id);
      return HttpResponse.json(marcos[id] ?? umMarcoSessao({ sessao_id: id }));
    }),
  );
}

describe("Painel de sessões", () => {
  it("lista as sessões com a próxima ação de cada uma, em linguagem do docente", async () => {
    backend({
      sessoes: [
        umaSessao({ id: 1, disciplina: "Algoritmos", estado: "rascunho" }),
        umaSessao({
          id: 2,
          disciplina: "Redes",
          periodo: "2026.1",
          tema_escopo: "Camada de transporte",
          estado: "banco_congelado",
        }),
      ],
      marcos: {
        1: umMarcoSessao({ sessao_id: 1, marco: "m1_materiais" }),
        2: umMarcoSessao({
          sessao_id: 2,
          marco: "m2_banco",
          bancos: [umMarcoBanco({ marco: "m6_provas" })],
        }),
      },
    });
    renderApp("/", { token: "t" });

    const algoritmos = (await screen.findByText("Algoritmos")).closest("li")!;
    expect(within(algoritmos).getByText("Rascunho")).toBeInTheDocument();
    expect(await within(algoritmos).findByText("Enviar materiais")).toBeInTheDocument();

    const redes = screen.getByText("Redes").closest("li")!;
    expect(within(redes).getByText("2026.1")).toBeInTheDocument();
    expect(within(redes).getByText("Camada de transporte")).toBeInTheDocument();
    expect(within(redes).getByText("Banco congelado")).toBeInTheDocument();
    expect(await within(redes).findByText("Montar provas")).toBeInTheDocument();
  });

  it("cada sessão leva à sua rota", async () => {
    backend({ sessoes: [umaSessao({ id: 7, disciplina: "Cálculo" })] });
    const { user, router } = renderApp("/", { token: "t" });

    const link = await screen.findByRole("link", { name: /Cálculo/ });
    expect(link).toHaveAttribute("href", "/sessoes/7");
    await user.click(link);

    // A rota da sessão redireciona para a tela do marco (aqui, M1: materiais).
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/7/materiais"),
    );
  });

  it("estado vazio convida a criar a primeira sessão", async () => {
    backend({ sessoes: [] });
    const { user, router } = renderApp("/", { token: "t" });

    expect(
      await screen.findByText(/ainda não criou nenhuma sessão/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Criar primeira sessão" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/nova"),
    );
  });

  it("tem atalho para nova sessão quando já existem sessões", async () => {
    backend({ sessoes: [umaSessao()] });
    renderApp("/", { token: "t" });

    expect(await screen.findByRole("link", { name: "Nova sessão" })).toHaveAttribute(
      "href",
      "/sessoes/nova",
    );
  });

  it("pagina de 20 em 20 e a página cheia oferece a próxima", async () => {
    const consultas: string[] = [];
    const vinte = Array.from({ length: 20 }, (_, i) =>
      umaSessao({ id: i + 1, disciplina: `Disciplina ${i + 1}` }),
    );
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, ({ request }) => {
        const url = new URL(request.url);
        consultas.push(`${url.searchParams.get("limit")}/${url.searchParams.get("offset")}`);
        return HttpResponse.json(
          url.searchParams.get("offset") === "0"
            ? vinte
            : [umaSessao({ id: 21, disciplina: "Disciplina 21" })],
        );
      }),
      http.get(`${API}/sessoes/:id/marco`, ({ params }) =>
        HttpResponse.json(umMarcoSessao({ sessao_id: Number(params.id) })),
      ),
    );
    const { user } = renderApp("/", { token: "t" });

    expect(await screen.findByText("Disciplina 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Página anterior" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Próxima página" }));

    expect(await screen.findByText("Disciplina 21")).toBeInTheDocument();
    expect(consultas).toEqual(["20/0", "20/20"]);
    expect(screen.getByRole("button", { name: "Próxima página" })).toBeDisabled();
  });

  it("não derruba a lista quando o marco de uma sessão falha", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () => HttpResponse.json([umaSessao()])),
      http.get(`${API}/sessoes/:id/marco`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );
    renderApp("/", { token: "t" });

    expect(await screen.findByText("Algoritmos")).toBeInTheDocument();
    expect(
      await screen.findByText("Não foi possível consultar o andamento."),
    ).toBeInTheDocument();
  });

  it("mostra o erro da API quando a lista não carrega", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () =>
        HttpResponse.json({ detail: "Falha no banco" }, { status: 500 }),
      ),
    );
    renderApp("/", { token: "t" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Falha no banco");
  });
});
