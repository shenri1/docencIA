import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { DOCENTE, umaOrientacao, umaSessao } from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

function abrir({
  sessoes = [] as ReturnType<typeof umaSessao>[],
  orientacoes = [] as ReturnType<typeof umaOrientacao>[],
  aoPedirOrientacoes = (_sessaoId: string) => {},
} = {}) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes`, () => HttpResponse.json(sessoes)),
    http.get(`${API}/sessoes/:id/orientacoes`, ({ params }) => {
      aoPedirOrientacoes(String(params.id));
      return HttpResponse.json(orientacoes);
    }),
  );
  return renderApp("/sessoes/nova", { token: "t" });
}

async function trocar(
  user: ReturnType<typeof renderApp>["user"],
  rotulo: string,
  valor: string,
) {
  const campo = await screen.findByLabelText(rotulo);
  await user.clear(campo);
  await user.type(campo, valor);
}

describe("Nova sessão — parâmetros", () => {
  it("abre com os padrões: K=5 e 10/60/30, somando 100%", async () => {
    abrir();

    expect(await screen.findByLabelText("Alternativas por questão (K)")).toHaveValue(5);
    expect(screen.getByLabelText("Fáceis (%)")).toHaveValue(10);
    expect(screen.getByLabelText("Médias (%)")).toHaveValue(60);
    expect(screen.getByLabelText("Difíceis (%)")).toHaveValue(30);
    expect(screen.getByText("Soma: 100%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar sessão e continuar" })).toBeEnabled();
  });

  it("desabilita o envio e explica quando a soma não é 100", async () => {
    const { user } = abrir();

    await trocar(user, "Difíceis (%)", "20");

    expect(screen.getByText(/Soma: 90%/)).toHaveTextContent(/precisa ser 100%/);
    expect(screen.getByRole("button", { name: "Criar sessão e continuar" })).toBeDisabled();
  });

  it("cria a sessão e segue para os materiais", async () => {
    let corpo: unknown = null;
    server.use(
      http.post(`${API}/sessoes`, async ({ request }) => {
        corpo = await request.json();
        return HttpResponse.json(umaSessao({ id: 42 }), { status: 201 });
      }),
    );
    const { user, router } = abrir();

    await trocar(user, "Disciplina", "Algoritmos");
    await trocar(user, "Período letivo", "2026.2");
    await trocar(user, "Tema ou escopo (opcional)", "Ordenação");
    await user.click(screen.getByRole("button", { name: "Criar sessão e continuar" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/42/materiais"),
    );
    expect(corpo).toEqual({
      disciplina: "Algoritmos",
      periodo: "2026.2",
      tema_escopo: "Ordenação",
      area_do_conhecimento: null,
      k_alternativas: 5,
      p_f: 10,
      p_m: 60,
      p_d: 30,
      orientacoes: [],
    });
  });

  it("exige disciplina e período antes de enviar", async () => {
    const { user } = abrir();

    await user.click(await screen.findByRole("button", { name: "Criar sessão e continuar" }));

    expect(await screen.findByText("Informe a disciplina.")).toBeInTheDocument();
    expect(screen.getByText("Informe o período letivo, por exemplo 2026.2.")).toBeInTheDocument();
  });

  it("recusa K fora de 2 a 11", async () => {
    const { user } = abrir();

    await trocar(user, "Disciplina", "Algoritmos");
    await trocar(user, "Período letivo", "2026.2");
    await trocar(user, "Alternativas por questão (K)", "12");
    await user.click(screen.getByRole("button", { name: "Criar sessão e continuar" }));

    expect(await screen.findByText("Use de 2 a 11 alternativas.")).toBeInTheDocument();
  });

  it("mostra a recusa da API, que continua sendo a autoridade", async () => {
    server.use(
      http.post(`${API}/sessoes`, () =>
        HttpResponse.json(
          {
            detail: "pF + pM + pD deve somar exatamente 100%. Recebido pF=10, pM=60, pD=30 — soma 100.",
            codigo: "PARAMETROS_INCONSISTENTES",
            soma: 100,
          },
          { status: 422 },
        ),
      ),
    );
    const { user, router } = abrir();

    await trocar(user, "Disciplina", "Algoritmos");
    await trocar(user, "Período letivo", "2026.2");
    await user.click(screen.getByRole("button", { name: "Criar sessão e continuar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/pF \+ pM \+ pD/);
    expect(router.state.location.pathname).toBe("/sessoes/nova");
  });

  it("deixa voltar ao painel sem criar nada", async () => {
    server.use(http.get(`${API}/sessoes`, () => HttpResponse.json([])));
    const { user, router } = abrir();

    await user.click(await screen.findByRole("link", { name: "Cancelar" }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/sessoes"));
  });
});

describe("Nova sessão — orientações", () => {
  it("pré-preenche com as orientações de sessão ativas da sessão mais recente", async () => {
    let pedida: string | null = null;
    abrir({
      sessoes: [umaSessao({ id: 3 }), umaSessao({ id: 8 })],
      aoPedirOrientacoes: (id) => {
        pedida = id;
      },
      orientacoes: [
        umaOrientacao({ id: 1, o_que_mudar: "Prefiro exemplos práticos" }),
        umaOrientacao({ id: 2, o_que_mudar: "Desativada", estado: "inativa" }),
        umaOrientacao({
          id: 3,
          origem: "questao",
          estado: "ativa",
          o_que_mudar: "Veio de uma variação",
          banco_id: 4,
          numero_origem: 2,
        }),
      ],
    });

    expect(await screen.findByLabelText("Orientação 1")).toHaveValue("Prefiro exemplos práticos");
    expect(screen.queryByLabelText("Orientação 2")).not.toBeInTheDocument();
    expect(screen.getByText("Trazidas da sua última sessão.")).toBeInTheDocument();
    expect(pedida).toBe("8");
  });

  it("sem sessão anterior, começa com um campo vazio", async () => {
    abrir();
    expect(await screen.findByLabelText("Orientação 1")).toHaveValue("");
    expect(screen.queryByText("Trazidas da sua última sessão.")).not.toBeInTheDocument();
  });

  it("envia as orientações preenchidas, aparadas e sem as vazias", async () => {
    let corpo: { orientacoes?: string[] } | null = null;
    const { user } = abrir();
    server.use(
      http.post(`${API}/sessoes`, async ({ request }) => {
        corpo = (await request.json()) as { orientacoes?: string[] };
        return HttpResponse.json(umaSessao({ id: 42 }), { status: 201 });
      }),
    );

    await trocar(user, "Disciplina", "Algoritmos");
    await trocar(user, "Período letivo", "2026.2");
    await user.type(screen.getByLabelText("Orientação 1"), "  Gosto de exemplos práticos ");
    await user.click(screen.getByRole("button", { name: "Acrescentar orientação" }));
    await user.click(screen.getByRole("button", { name: "Criar sessão e continuar" }));

    await waitFor(() => expect(corpo).not.toBeNull());
    expect(corpo!.orientacoes).toEqual(["Gosto de exemplos práticos"]);
  });

  it("permite no máximo 5 e remove", async () => {
    const { user } = abrir();
    await screen.findByLabelText("Orientação 1");
    const acrescentar = screen.getByRole("button", { name: "Acrescentar orientação" });
    for (let i = 0; i < 4; i++) {
      await user.click(acrescentar);
      // O Botao ignora o segundo clique dentro de 400 ms (trava de duplo clique).
      await new Promise((r) => setTimeout(r, 450));
    }

    expect(screen.getByLabelText("Orientação 5")).toBeInTheDocument();
    expect(acrescentar).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Remover orientação 5" }));
    expect(screen.queryByLabelText("Orientação 5")).not.toBeInTheDocument();
    expect(acrescentar).toBeEnabled();
  });
});
