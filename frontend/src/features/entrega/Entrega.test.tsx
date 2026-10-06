import { screen, waitFor, within } from "@testing-library/react";
import { type BancoFalso, montarFalso } from "../../mocks/backendFalso";
import { server } from "../../mocks/server";
import { comBanco, TOKEN } from "../../test/comBanco";
import { renderApp } from "../../test/renderApp";

/** Banco 7 congelado com provas: A = objetivas 1–5 e discursiva 13; B = 6–10 e 14. */
function comProvas(): BancoFalso {
  const banco = comBanco({ objetivas: 12, discursivas: 2, estado: "congelado" });
  montarFalso(banco, 5, 1);
  return banco;
}

const abrir = () => renderApp("/sessoes/5/entrega", { token: TOKEN });
const gabarito = (nome: string) => screen.findByRole("region", { name: nome });
const itemComentado = (versao: "A" | "B", posicao: number) =>
  screen.findByRole("article", { name: `Gabarito da Prova ${versao}, posição ${posicao}` });

describe("Entrega — gabaritos", () => {
  it("antes do M10 orienta a montar as provas", async () => {
    comBanco({ estado: "congelado" });
    abrir();

    expect(await screen.findByText(/Monte as provas antes/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir para as provas" })).toHaveAttribute(
      "href",
      "/sessoes/5/provas",
    );
  });

  it("o simples da Prova A mostra posição e letra, e aspectos na discursiva", async () => {
    comProvas();
    abrir();

    const simples = await gabarito("Gabarito simples da Prova A");
    const linhas = within(simples).getAllByRole("row");
    expect(linhas[1]).toHaveTextContent("1Questão 1 do bancoB");
    expect(linhas[6]).toHaveTextContent("Aspecto esperado da questão 13");
    expect(within(simples).queryByText(/Justificativa da correta/)).not.toBeInTheDocument();
  });

  it("trocar prova e modalidade pede só o selecionado", async () => {
    comProvas();
    const pedidos: string[] = [];
    server.events.on("request:start", ({ request }) => {
      const url = new URL(request.url);
      if (url.pathname.endsWith("/gabarito")) pedidos.push(`${url.pathname}${url.search}`);
    });
    try {
      const { user } = abrir();

      await gabarito("Gabarito simples da Prova A");
      await user.click(screen.getByRole("button", { name: "Comentado" }));
      await gabarito("Gabarito comentado da Prova A");
      await user.click(screen.getByRole("button", { name: "Prova B" }));
      const b = await gabarito("Gabarito comentado da Prova B");

      expect(within(b).getByText("Questão 6 do banco")).toBeInTheDocument();
      expect(pedidos).toEqual([
        "/provas/71/gabarito?modalidade=simples",
        "/provas/71/gabarito?modalidade=comentado",
        "/provas/72/gabarito?modalidade=comentado",
      ]);
    } finally {
      server.events.removeAllListeners("request:start");
    }
  });

  it("o comentado mostra justificativa, invalidações, aspectos e fontes", async () => {
    comProvas();
    const { user } = abrir();

    await user.click(await screen.findByRole("button", { name: "Comentado" }));

    const primeira = await itemComentado("A", 1);
    expect(within(primeira).getByText("Correta: B")).toBeInTheDocument();
    expect(within(primeira).getByText("Justificativa da correta da questão 1.")).toBeInTheDocument();
    expect(within(primeira).getByText("A) Motivo do distrator 1 da questão 1.")).toBeInTheDocument();
    expect(within(primeira).getByText(/Trecho do material que sustenta a questão 1/)).toBeInTheDocument();

    const discursiva = await itemComentado("A", 6);
    expect(within(discursiva).getByText("Objetivo cognitivo da questão 13.")).toBeInTheDocument();
    expect(within(discursiva).getByText(/Aspecto esperado da questão 13/)).toBeInTheDocument();
  });

  it("avisos do gabarito", async () => {
    const banco = comProvas();
    banco.provas!.gabarito = { citaLetra: [1], semLetra: [2], incompleto: true };
    banco.revisao = 4;
    const { user } = abrir();

    await user.click(await screen.findByRole("button", { name: "Comentado" }));

    expect(
      within(await itemComentado("A", 1)).getByText(/cita a letra de uma alternativa/),
    ).toBeInTheDocument();
    const segunda = await itemComentado("A", 2);
    expect(within(segunda).getByText(/não diz qual motivo é de qual alternativa/)).toBeInTheDocument();
    expect(within(segunda).getByText("Motivo do distrator 1 da questão 2.")).toBeInTheDocument();
    expect(screen.getByText(/Gabarito incompleto/)).toBeInTheDocument();
    expect(screen.getByText(/O banco mudou desde a montagem/)).toBeInTheDocument();
  });
});

const arquivo = (nome: string) => screen.findByRole("article", { name: nome });

describe("Entrega — exportação", () => {
  afterEach(() => vi.restoreAllMocks());

  it("exportar mostra os dois arquivos e repetir não duplica", async () => {
    const banco = comProvas();
    const { user } = abrir();

    expect(await screen.findByText("Nenhum arquivo foi gerado ainda.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Exportar DOCX" }));

    const puro = await arquivo("Conteúdo puro, revisão r0");
    expect(within(puro).getByText(`sha256: ${"a".repeat(60)}0000`)).toBeInTheDocument();
    expect(await arquivo("Metadados, revisão r0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Exportar DOCX" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Exportar DOCX" })).toBeEnabled());
    expect(screen.getAllByRole("article", { name: /, revisão r0$/ })).toHaveLength(2);
    expect(banco.exportacoes).toHaveLength(2);
  });

  it("409 mostra a lista de problemas", async () => {
    const banco = comProvas();
    banco.problemasExportacao = ["A verificação pós-montagem tem violação."];
    const { user } = abrir();

    await user.click(await screen.findByRole("button", { name: "Exportar DOCX" }));

    expect(await screen.findByText(/estado incoerente/)).toBeInTheDocument();
    expect(screen.getByText("A verificação pós-montagem tem violação.")).toBeInTheDocument();
    expect(banco.exportacoes ?? []).toHaveLength(0);
  });

  it("baixar dispara o download com o nome do cabeçalho", async () => {
    const banco = comProvas();
    banco.exportacoes = [
      {
        id: 1,
        tipo: "conteudo_puro",
        revisao_banco: 0,
        hash_conteudo: "c".repeat(64),
        criado_em: "2026-10-05T12:00:00Z",
      },
    ];
    const criar = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:falso");
    const liberar = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const nomes: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      nomes.push(this.download);
    });
    const { user } = abrir();

    await user.click(
      within(await arquivo("Conteúdo puro, revisão r0")).getByRole("button", { name: "Baixar" }),
    );

    await waitFor(() => expect(nomes).toEqual(["prova-banco7-r0-conteudo_puro.docx"]));
    // Não `expect.any(Blob)`: o Blob da resposta pode vir de outra classe que a do happy-dom.
    expect(criar).toHaveBeenCalledTimes(1);
    expect(liberar).toHaveBeenCalledWith("blob:falso");
  });

  it("erro no download aparece junto do arquivo", async () => {
    const banco = comProvas();
    banco.exportacoes = [
      {
        id: 1,
        tipo: "metadados",
        revisao_banco: 0,
        hash_conteudo: "d".repeat(64),
        criado_em: "2026-10-05T12:00:00Z",
        corrompida: true,
      },
    ];
    const { user } = abrir();

    const metadados = await arquivo("Metadados, revisão r0");
    await user.click(within(metadados).getByRole("button", { name: "Baixar" }));

    expect(await within(metadados).findByRole("alert")).toHaveTextContent(/não confere/);
  });

  it("o histórico agrupa por revisão, da mais recente para a mais antiga", async () => {
    const banco = comProvas();
    banco.exportacoes = [0, 2].flatMap((revisao) =>
      (["conteudo_puro", "metadados"] as const).map((tipo, i) => ({
        id: revisao * 10 + i,
        tipo,
        revisao_banco: revisao,
        hash_conteudo: "e".repeat(64),
        criado_em: "2026-10-05T12:00:00Z",
      })),
    );
    abrir();

    const revisoes = await screen.findAllByRole("heading", { name: /^Revisão r\d$/ });
    expect(revisoes.map((h) => h.textContent)).toEqual(["Revisão r2", "Revisão r0"]);
  });
});
