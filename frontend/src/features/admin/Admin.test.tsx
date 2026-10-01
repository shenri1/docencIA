import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { Prompt, RegistroAuditoria } from "../../api/tipos";
import { server } from "../../mocks/server";
import { DOCENTE } from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

const ADMIN = { ...DOCENTE, perfil: "administrador" as const };

function umPrompt(sobrescrever: Partial<Prompt> = {}): Prompt {
  return {
    id: 1,
    versao: "1.0.0",
    papel_definido: "docente universitário elaborador de questões",
    conteudo: "Você é um docente universitário…",
    hash_modulos: "a".repeat(64),
    ativo: true,
    criado_em: "2026-10-01T12:00:00Z",
    ...sobrescrever,
  };
}

function umEvento(sobrescrever: Partial<RegistroAuditoria> = {}): RegistroAuditoria {
  return {
    id: 1,
    tipo_evento: "exclusao",
    entidade_afetada: "bancos_questoes:3",
    ator: "b".repeat(64),
    payload: { numeros: [2], revisao: 1 },
    timestamp: "2026-10-01T12:00:00Z",
    ...sobrescrever,
  };
}

function comoAdmin() {
  server.use(http.get(`${API}/auth/me`, () => HttpResponse.json(ADMIN)));
}

describe("Administração — acesso", () => {
  it("o cabeçalho mostra Administração só para o administrador", async () => {
    comoAdmin();
    server.use(http.get(`${API}/sessoes`, () => HttpResponse.json([])));
    renderApp("/", { token: "t" });

    expect(await screen.findByRole("link", { name: "Administração" })).toHaveAttribute(
      "href",
      "/admin/prompts",
    );
  });

  it("o docente comum não vê o link", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes`, () => HttpResponse.json([])),
    );
    renderApp("/", { token: "t" });

    expect(await screen.findByText(DOCENTE.nome)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Administração" })).not.toBeInTheDocument();
  });

  it("o docente comum que abre /admin vê o aviso, não a tela", async () => {
    server.use(http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)));
    renderApp("/admin/prompts", { token: "t" });

    expect(await screen.findByText("Esta área é só para administradores.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Prompt mestre" })).not.toBeInTheDocument();
  });

  it("/admin leva aos prompts", async () => {
    comoAdmin();
    server.use(http.get(`${API}/prompts`, () => HttpResponse.json([])));
    const { router } = renderApp("/admin", { token: "t" });

    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/prompts"));
  });
});

describe("Administração — prompt mestre", () => {
  it("lista as versões e marca a ativa", async () => {
    comoAdmin();
    server.use(
      http.get(`${API}/prompts`, () =>
        HttpResponse.json([
          umPrompt({ id: 2, versao: "1.1.0", ativo: false }),
          umPrompt({ id: 1, versao: "1.0.0", ativo: true }),
        ]),
      ),
    );
    renderApp("/admin/prompts", { token: "t" });

    const nova = (await screen.findByText("1.1.0")).closest("li")!;
    const ativa = screen.getByText("1.0.0").closest("li")!;
    expect(within(ativa).getByText("Ativa")).toBeInTheDocument();
    expect(within(ativa).queryByRole("button", { name: /Ativar/ })).not.toBeInTheDocument();
    expect(within(nova).getByRole("button", { name: "Ativar 1.1.0" })).toBeInTheDocument();
    expect(within(ativa).getByText("aaaaaaaaaaaa")).toBeInTheDocument();
  });

  it("ativar pede confirmação e chama a API", async () => {
    comoAdmin();
    let ativa = "1.0.0";
    const pedidos: string[] = [];
    server.use(
      http.get(`${API}/prompts`, () =>
        HttpResponse.json([
          umPrompt({ id: 2, versao: "1.1.0", ativo: ativa === "1.1.0" }),
          umPrompt({ id: 1, versao: "1.0.0", ativo: ativa === "1.0.0" }),
        ]),
      ),
      http.post(`${API}/prompts/:versao/ativar`, ({ params }) => {
        pedidos.push(String(params.versao));
        ativa = String(params.versao);
        return HttpResponse.json(umPrompt({ id: 2, versao: ativa, ativo: true }));
      }),
    );
    const { user } = renderApp("/admin/prompts", { token: "t" });

    await user.click(await screen.findByRole("button", { name: "Ativar 1.1.0" }));
    expect(pedidos).toEqual([]);
    expect(screen.getByText(/todas as próximas gerações/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar ativação" }));

    await waitFor(() => expect(pedidos).toEqual(["1.1.0"]));
    const nova = (await screen.findByText("1.1.0")).closest("li")!;
    expect(await within(nova).findByText("Ativa")).toBeInTheDocument();
  });

  it("registra uma versão com os marcadores preenchidos", async () => {
    comoAdmin();
    let corpo: Record<string, unknown> | null = null;
    server.use(
      http.get(`${API}/prompts`, () => HttpResponse.json([umPrompt()])),
      http.post(`${API}/prompts`, async ({ request }) => {
        corpo = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(umPrompt({ id: 2, versao: "1.1.0", ativo: false }), {
          status: 201,
        });
      }),
    );
    const { user } = renderApp("/admin/prompts", { token: "t" });

    await user.type(await screen.findByLabelText("Versão"), "1.1.0");
    await user.click(screen.getByRole("button", { name: "Registrar versão" }));

    expect(await screen.findByText(/Versão 1.1.0 registrada/)).toBeInTheDocument();
    expect(corpo).toMatchObject({
      versao: "1.1.0",
      papel_definido: "docente universitário elaborador de questões",
      disciplina: "(definida em cada sessão)",
      periodo: "(definido em cada sessão)",
      k_alternativas: 5,
      n_faceis: 0,
      n_medias: 0,
      n_dificeis: 0,
    });
  });

  it("mostra a recusa da API ao registrar versão repetida", async () => {
    comoAdmin();
    server.use(
      http.get(`${API}/prompts`, () => HttpResponse.json([umPrompt()])),
      http.post(`${API}/prompts`, () =>
        HttpResponse.json(
          { detail: "A versão 1.0.0 já existe.", codigo: "VERSAO_PROMPT_DUPLICADA" },
          { status: 409 },
        ),
      ),
    );
    const { user } = renderApp("/admin/prompts", { token: "t" });

    await user.type(await screen.findByLabelText("Versão"), "1.0.0");
    await user.click(screen.getByRole("button", { name: "Registrar versão" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A versão 1.0.0 já existe.");
  });
});

describe("Administração — log de auditoria", () => {
  it("lista os eventos com o ator pseudonimizado", async () => {
    comoAdmin();
    server.use(
      http.get(`${API}/admin/logs`, () =>
        HttpResponse.json([
          umEvento({ id: 2, tipo_evento: "login_falho", entidade_afetada: "docentes", ator: null }),
          umEvento({ id: 1 }),
        ]),
      ),
    );
    renderApp("/admin/logs", { token: "t" });

    // O filtro de tipo também lista "Login falho" e "Exclusão": busca só na tabela.
    const tabela = await screen.findByRole("table");
    expect(within(tabela).getByText("Login falho")).toBeInTheDocument();
    expect(within(tabela).getByText("Exclusão")).toBeInTheDocument();
    expect(within(tabela).getByText("bancos_questoes:3")).toBeInTheDocument();
    expect(within(tabela).getByText("bbbbbbbbbb…")).toBeInTheDocument();
  });

  it("filtra por tipo e pagina de 50 em 50", async () => {
    comoAdmin();
    const consultas: URLSearchParams[] = [];
    server.use(
      http.get(`${API}/admin/logs`, ({ request }) => {
        const busca = new URL(request.url).searchParams;
        consultas.push(busca);
        const total = busca.get("deslocamento") === "50" ? 3 : 50;
        return HttpResponse.json(
          Array.from({ length: total }, (_, i) => umEvento({ id: 1000 - i })),
        );
      }),
    );
    const { user } = renderApp("/admin/logs", { token: "t" });

    await screen.findByRole("table");
    expect(consultas.at(-1)?.get("limite")).toBe("50");
    expect(screen.getByRole("button", { name: "Anteriores" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Seguintes" }));
    await waitFor(() => expect(consultas.at(-1)?.get("deslocamento")).toBe("50"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Seguintes" })).toBeDisabled(),
    );

    await user.selectOptions(screen.getByLabelText("Tipo de evento"), "login_falho");
    await waitFor(() => expect(consultas.at(-1)?.get("tipo_evento")).toBe("login_falho"));
    // Filtro novo volta à primeira página.
    expect(consultas.at(-1)?.get("deslocamento")).toBe("0");
  });
});
