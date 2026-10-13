import { screen, waitFor, within } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { questaoFalsa } from "../../mocks/backendFalso";
import { server } from "../../mocks/server";
import { umMarcoBanco, umMarcoSessao, umaOrientacao } from "../../test/fixtures";
import { comBanco } from "../../test/comBanco";
import { API, renderApp } from "../../test/renderApp";

// DOCENTE.id é 1, e o falso reconhece o token "mock-token-<id>".
const abrirMesa = () => renderApp("/sessoes/5/banco", { token: "mock-token-1" });
const cartao = (numero: number) => screen.findByRole("article", { name: `Questão ${numero}` });

async function pedirVariacao(
  user: ReturnType<typeof renderApp>["user"],
  numero: number,
  campos: { articular?: string; mudar?: string; acumular?: boolean } = {},
) {
  const alvo = await cartao(numero);
  await user.click(within(alvo).getByRole("button", { name: "Pedir variação" }));
  if (campos.articular) {
    await user.type(
      within(alvo).getByLabelText("Articular com (um assunto do seu material)"),
      campos.articular,
    );
  }
  if (campos.mudar) await user.type(within(alvo).getByLabelText("O que mudar"), campos.mudar);
  if (campos.acumular) {
    await user.click(
      within(alvo).getByRole("checkbox", {
        name: "Aplicar também às próximas gerações desta sessão",
      }),
    );
  }
  const guiada = Boolean(campos.articular || campos.mudar);
  await user.click(
    within(alvo).getByRole("button", { name: guiada ? "Gerar variação" : "Gerar outra questão" }),
  );
}

describe("Mesa de curadoria — leitura", () => {
  it("mostra as questões ativas, com a correta marcada e as fontes", async () => {
    comBanco({ objetivas: 2, discursivas: 1 });
    abrirMesa();

    const primeira = await cartao(1);
    expect(within(primeira).getByText("Enunciado da questão 1.")).toBeInTheDocument();
    const correta = within(primeira).getByText("Alternativa B da questão 1").closest("li")!;
    expect(within(correta).getByText("Correta")).toBeInTheDocument();
    expect(within(primeira).getByText(/Trecho do material que sustenta a questão 1/)).toBeInTheDocument();

    const discursiva = await cartao(3);
    expect(within(discursiva).getByText(/Aspecto esperado da questão 3/)).toBeInTheDocument();

    expect(screen.getByText("v1.r0")).toBeInTheDocument();
    expect(screen.getByText("3 de 3 questões ativas")).toBeInTheDocument();
  });

  it("lê o banco em blocos de 20", async () => {
    comBanco({ objetivas: 25 });
    const { user } = abrirMesa();

    await cartao(20);
    expect(screen.queryByRole("article", { name: "Questão 21" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "21–25" }));
    await cartao(21);
    expect(screen.queryByRole("article", { name: "Questão 1" })).not.toBeInTheDocument();
  });

  it("o filtro de histórico mostra as excluídas em leitura", async () => {
    const banco = comBanco();
    banco.questoes[0]!.estado = "excluida";
    const { user } = abrirMesa();

    await cartao(2);
    expect(screen.queryByRole("article", { name: "Questão 1" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Mostrar excluídas e substituídas" }));
    const excluida = await cartao(1);
    expect(within(excluida).getByText("Excluída")).toBeInTheDocument();
  });

  it("mostra o último relatório de impacto no painel", async () => {
    const banco = comBanco();
    banco.ultimo_relatorio = {
      revisao: 0,
      evento: "exclusao",
      n_final: 3,
      contagem_por_faixa: { objetiva: { facil: 1, media: 1, dificil: 1 } },
      desvio_observado: {},
      alerta_desvio: true,
      timestamp: "2026-10-01T12:00:00Z",
    };
    abrirMesa();

    expect(
      await screen.findByText("Último relatório de impacto: exclusão na revisão r0, com 3 questões ativas."),
    ).toBeInTheDocument();
    expect(screen.getByText("Objetivas: fácil 1 · média 1 · difícil 1")).toBeInTheDocument();
    expect(screen.getByText(/se afastou mais de 5 pontos/)).toBeInTheDocument();
  });
});

describe("Mesa de curadoria — exclusões", () => {
  it("marcações sobrevivem à troca de bloco e são aplicadas juntas", async () => {
    const banco = comBanco({ objetivas: 25 });
    const { user } = abrirMesa();

    await user.click(within(await cartao(2)).getByRole("button", { name: "Marcar para exclusão" }));
    expect(within(await cartao(2)).getByText("Marcada para exclusão")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "21–25" }));
    await user.click(within(await cartao(22)).getByRole("button", { name: "Marcar para exclusão" }));
    expect(screen.getByText("2 marcadas para exclusão")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aplicar exclusões" }));
    expect(screen.getByText(/Excluir as questões 2, 22\?/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirmar exclusões" }));

    expect(
      await screen.findByText("Exclusões aplicadas. O banco está na revisão r1, com 23 questões ativas."),
    ).toBeInTheDocument();
    expect(banco.questoes.filter((q) => q.estado === "excluida").map((q) => q.numero)).toEqual([2, 22]);
    expect(
      await screen.findByText("Último relatório de impacto: exclusão na revisão r1, com 23 questões ativas."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "Questão 22" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aplicar exclusões" })).not.toBeInTheDocument();
  });

  it("Manter desfaz a marcação", async () => {
    comBanco();
    const { user } = abrirMesa();

    await user.click(within(await cartao(1)).getByRole("button", { name: "Marcar para exclusão" }));
    await user.click(within(await cartao(1)).getByRole("button", { name: "Manter" }));

    expect(within(await cartao(1)).getByText("Ativa")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aplicar exclusões" })).not.toBeInTheDocument();
  });

  it("revisão velha recarrega, avisa e mantém as marcações", async () => {
    const banco = comBanco();
    const { user } = abrirMesa();

    await user.click(within(await cartao(1)).getByRole("button", { name: "Marcar para exclusão" }));
    banco.revisao = 4; // outra janela mexeu no banco
    await user.click(screen.getByRole("button", { name: "Aplicar exclusões" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusões" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O banco mudou desde que você o viu. Confira e aplique de novo.",
    );
    expect(banco.questoes[0]!.estado).toBe("ativa");
    expect(screen.getByText("1 marcada para exclusão")).toBeInTheDocument();
    expect(await screen.findByText("v1.r4")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aplicar exclusões" }));
    await user.click(screen.getByRole("button", { name: "Confirmar exclusões" }));
    expect(
      await screen.findByText("Exclusões aplicadas. O banco está na revisão r5, com 2 questões ativas."),
    ).toBeInTheDocument();
  });
});

describe("Mesa de curadoria — variação", () => {
  it("pedir variação mostra a candidata ao lado e aceitar troca a questão", async () => {
    const banco = comBanco();
    const { user } = abrirMesa();

    await pedirVariacao(user, 1);
    const comparacao = await screen.findByRole("region", { name: "Variação da questão 1" });
    expect(within(comparacao).getByText("Enunciado da questão 1.")).toBeInTheDocument();
    expect(within(comparacao).getByText("Variação do enunciado da questão 1.")).toBeInTheDocument();

    await user.click(within(comparacao).getByRole("button", { name: "Aceitar variação" }));
    expect(
      await screen.findByText("Variação aceita. O banco está na revisão r1, com 3 questões ativas."),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByRole("region", { name: "Variação da questão 1" })).not.toBeInTheDocument(),
    );
    expect(within(await cartao(1)).getByText("Variação do enunciado da questão 1.")).toBeInTheDocument();
    expect(banco.questoes.filter((q) => q.numero === 1).map((q) => q.estado)).toEqual([
      "substituida",
      "ativa",
    ]);

    // Com histórico, a substituída e a nova ativa dividem o número 1.
    await user.click(screen.getByRole("checkbox", { name: "Mostrar excluídas e substituídas" }));
    const doUm = await screen.findAllByRole("article", { name: "Questão 1" });
    expect(doUm).toHaveLength(2);
    expect(within(doUm[0]!).getByText("Substituída")).toBeInTheDocument();
  });

  it("rejeitar mantém a original", async () => {
    const banco = comBanco();
    const { user } = abrirMesa();

    await pedirVariacao(user, 1);
    const comparacao = await screen.findByRole("region", { name: "Variação da questão 1" });
    await user.click(within(comparacao).getByRole("button", { name: "Rejeitar variação" }));

    expect(
      await screen.findByText("Variação rejeitada. A questão original continua no banco."),
    ).toBeInTheDocument();
    expect(within(await cartao(1)).getByText("Enunciado da questão 1.")).toBeInTheDocument();
    expect(banco.questoes.filter((q) => q.numero === 1).map((q) => q.estado)).toEqual([
      "ativa",
      "descartada",
    ]);
  });

  it("insuficiência de fonte aparece como orientação, sem candidata", async () => {
    comBanco({ versao: "insuf" });
    const { user } = abrirMesa();

    await pedirVariacao(user, 1);

    const orientacao = (await screen.findByText(/O material não sustentou outra questão/)).closest(
      "[role=status]",
    )!;
    expect(orientacao).toHaveTextContent("(slide 1)");
    expect(screen.queryByRole("region", { name: "Variação da questão 1" })).not.toBeInTheDocument();
  });

  it("recarregar com candidata pendente mostra a comparação sem pedir de novo", async () => {
    const banco = comBanco();
    banco.questoes.push({ ...questaoFalsa(2), estado: "candidata", enunciado: "Candidata guardada." });
    abrirMesa();

    const comparacao = await screen.findByRole("region", { name: "Variação da questão 2" });
    expect(within(comparacao).getByText("Candidata guardada.")).toBeInTheDocument();
  });

  it("um pedido de variação por vez", async () => {
    comBanco();
    server.use(
      http.post(`${API}/bancos/7/questoes/:numero/substituicao`, async ({ params }) => {
        await delay(100);
        return HttpResponse.json({
          numero: Number(params.numero),
          candidata: null,
          motivo_insuficiencia: "o trecho não sustenta outra questão",
          localizacao: null,
        });
      }),
    );
    const { user } = abrirMesa();

    await pedirVariacao(user, 1);

    expect(
      await within(await cartao(1)).findByRole("button", { name: "Gerando variação…" }),
    ).toBeDisabled();
    expect(within(await cartao(2)).getByRole("button", { name: "Pedir variação" })).toBeDisabled();
    expect(await screen.findByText(/O material não sustentou outra questão/)).toBeInTheDocument();
    await waitFor(async () =>
      expect(within(await cartao(2)).getByRole("button", { name: "Pedir variação" })).toBeEnabled(),
    );
  });

  it("com prova montada não oferece variação e diz por quê", async () => {
    comBanco();
    server.use(
      http.get(`${API}/sessoes/5/marco`, () =>
        HttpResponse.json(
          umMarcoSessao({
            sessao_id: 5,
            marco: "m10_docx",
            bancos: [umMarcoBanco({ banco_id: 7, marco: "m10_docx", n_alvo: 3, n_atual: 3 })],
          }),
        ),
      ),
    );
    abrirMesa();

    const primeira = await cartao(1);
    expect(within(primeira).queryByRole("button", { name: "Pedir variação" })).not.toBeInTheDocument();
    expect(screen.getByText(/provas já foram montadas/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver provas" })).toHaveAttribute(
      "href",
      "/sessoes/5/provas",
    );
  });
});

describe("Mesa de curadoria — congelar", () => {
  it("congelar pede confirmação e deixa a mesa em leitura para exclusões", async () => {
    const banco = comBanco();
    const { user } = abrirMesa();

    await user.click(await screen.findByRole("button", { name: "Congelar banco" }));
    expect(screen.getByText(/fecha a janela de exclusões/)).toBeInTheDocument();
    expect(banco.estado).toBe("aberto");
    await user.click(screen.getByRole("button", { name: "Confirmar congelamento" }));

    expect(
      await screen.findByText("Banco congelado na revisão r1, com 3 questões ativas."),
    ).toBeInTheDocument();
    expect(banco.estado).toBe("congelado");
    expect(await screen.findByRole("link", { name: "Montar provas" })).toHaveAttribute(
      "href",
      "/sessoes/5/provas",
    );
    const primeira = await cartao(1);
    expect(within(primeira).queryByRole("button", { name: "Marcar para exclusão" })).not.toBeInTheDocument();
    expect(within(primeira).getByRole("button", { name: "Pedir variação" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Congelar banco" })).not.toBeInTheDocument();
  });

  it("marcações pendentes bloqueiam o congelamento", async () => {
    comBanco();
    const { user } = abrirMesa();

    await user.click(within(await cartao(1)).getByRole("button", { name: "Marcar para exclusão" }));

    expect(screen.getByRole("button", { name: "Congelar banco" })).toBeDisabled();
    expect(
      screen.getByText("Aplique ou desmarque a exclusão marcada antes de congelar."),
    ).toBeInTheDocument();
  });
});

describe("Mesa de curadoria — entrada da auditoria", () => {
  it("oferece o link com o banco aberto e com o banco congelado", async () => {
    comBanco();
    abrirMesa();
    expect(await screen.findByRole("link", { name: "Auditar o banco" })).toHaveAttribute(
      "href",
      "/sessoes/5/auditoria",
    );
  });

  it("oferece o link também depois de congelar", async () => {
    const banco = comBanco();
    banco.estado = "congelado";
    abrirMesa();
    expect(await screen.findByRole("link", { name: "Auditar o banco" })).toBeInTheDocument();
  });

  it("não oferece o link quando o banco não tem objetivas ativas", async () => {
    comBanco({ objetivas: 0, discursivas: 2 });
    abrirMesa();
    await cartao(1);
    expect(screen.queryByRole("link", { name: "Auditar o banco" })).not.toBeInTheDocument();
  });
});

describe("Mesa de curadoria — variação guiada e orientações", () => {
  it("variação guiada manda articular, mudar e acumular", async () => {
    comBanco();
    let corpo: unknown = null;
    server.use(
      http.post(`${API}/bancos/7/questoes/:numero/substituicao`, async ({ request }) => {
        corpo = await request.clone().json();
        // Sem retorno: o MSW segue para o handler do backend falso.
      }),
    );
    const { user } = abrirMesa();

    await pedirVariacao(user, 1, { articular: "redes", mudar: "use um roteador", acumular: true });

    const comparacao = await screen.findByRole("region", { name: "Variação da questão 1" });
    expect(corpo).toEqual({ cruzar_com: "redes", o_que_mudar: "use um roteador", acumular: true });
    // find*: o texto depende da lista de orientações, recarregada depois do pedido.
    expect(
      await within(comparacao).findByText(
        "Orientações: Articular com: redes. Mudar: use um roteador",
      ),
    ).toBeInTheDocument();
  });

  it("sem texto pede outra questão sem corpo", async () => {
    comBanco();
    let corpo: string | null = null;
    server.use(
      http.post(`${API}/bancos/7/questoes/:numero/substituicao`, async ({ request }) => {
        corpo = await request.clone().text();
      }),
    );
    const { user } = abrirMesa();

    await pedirVariacao(user, 1);

    await screen.findByRole("region", { name: "Variação da questão 1" });
    expect(corpo).toBe("");
  });

  it("insuficiência com articular diz o assunto no título", async () => {
    comBanco({ versao: "insuf" });
    const { user } = abrirMesa();

    await pedirVariacao(user, 1, { articular: "redes" });

    expect(
      await screen.findByText("O material não sustentou a relação com redes"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Variação da questão 1" })).not.toBeInTheDocument();
  });

  it("variação acumulada no teto mostra o limite e não gera", async () => {
    comBanco({
      orientacoes: Array.from({ length: 5 }, (_, i) =>
        umaOrientacao({ id: i + 1, o_que_mudar: `orientação ${i + 1}` }),
      ),
    });
    const { user } = abrirMesa();

    await pedirVariacao(user, 1, { mudar: "mais uma", acumular: true });

    expect(await screen.findByText(/máximo de orientações ativas/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Variação da questão 1" })).not.toBeInTheDocument();
  });

  it("o cartão mostra as orientações vigentes na geração", async () => {
    const banco = comBanco({
      orientacoes: [umaOrientacao({ id: 4, o_que_mudar: "exemplos práticos" })],
    });
    banco.questoes[0]!.orientacoes_ids = [4];
    abrirMesa();

    // find*: o cartão chega antes da lista de orientações.
    expect(
      await within(await cartao(1)).findByText("Orientações: Mudar: exemplos práticos"),
    ).toBeInTheDocument();
    expect(within(await cartao(2)).queryByText(/Orientações:/)).not.toBeInTheDocument();
  });

  it("o painel fica recolhido na mesa e funciona ao abrir", async () => {
    comBanco();
    const { user } = abrirMesa();

    await user.click(await screen.findByText("Orientações da sessão (0 ativas)"));
    const painel = screen.getByRole("region", { name: "Orientações da sessão" });
    await user.type(within(painel).getByLabelText("Nova orientação"), "Enunciados curtos");
    await user.click(within(painel).getByRole("button", { name: "Acrescentar" }));

    expect(await within(painel).findByText("Mudar: Enunciados curtos")).toBeInTheDocument();
  });
});
