import { screen, waitFor, within } from "@testing-library/react";
import { montarFalso } from "../../mocks/backendFalso";
import { comBanco, TOKEN } from "../../test/comBanco";
import { renderApp } from "../../test/renderApp";

const abrir = () => renderApp("/sessoes/5/provas", { token: TOKEN });
const prova = (versao: "A" | "B") => screen.findByRole("region", { name: `Prova ${versao}` });
const item = (versao: "A" | "B", posicao: number) =>
  screen.findByRole("article", { name: `Prova ${versao}, posição ${posicao}` });

describe("Provas — ver (M10)", () => {
  it("recarregar no M10 mostra as duas provas", async () => {
    const banco = comBanco({ objetivas: 20, estado: "congelado" });
    montarFalso(banco, 10, 0);
    abrir();

    const a = await prova("A");
    const b = await prova("B");
    expect(within(a).getByText("10 questões: 10 objetivas e 0 discursivas")).toBeInTheDocument();
    expect(within(b).getByText("10 questões: 10 objetivas e 0 discursivas")).toBeInTheDocument();

    const primeira = await item("A", 1);
    expect(within(primeira).getByText("Questão 1 do banco")).toBeInTheDocument();
    expect(within(primeira).getByText("Enunciado da questão 1.")).toBeInTheDocument();
    expect(within(primeira).getByText("Alternativa B da questão 1")).toBeInTheDocument();
    // prova não diz qual é a correta.
    expect(screen.queryByText("Correta")).not.toBeInTheDocument();

    expect(screen.getByText("Montadas sobre a revisão r0 do banco.")).toBeInTheDocument();
    expect(screen.getByText(/Verificação sem violações/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Exportar provas" })).toHaveAttribute(
      "href",
      "/sessoes/5/entrega",
    );
  });

  it("compartilhadas aparecem marcadas nas duas colunas", async () => {
    const banco = comBanco({ objetivas: 15, estado: "congelado" });
    montarFalso(banco, 10, 0); // A: 1–10; B: 11–15 e 1–5
    abrir();

    expect(within(await item("A", 1)).getByText("Também na Prova B")).toBeInTheDocument();
    expect(within(await item("A", 6)).queryByText("Também na Prova B")).not.toBeInTheDocument();
    const sexta = await item("B", 6);
    expect(within(sexta).getByText("Questão 1 do banco")).toBeInTheDocument();
    expect(within(sexta).getByText("Também na Prova A")).toBeInTheDocument();
  });

  it("sem_subtema e prova desatualizada viram aviso", async () => {
    const banco = comBanco({ objetivas: 20, estado: "congelado" });
    montarFalso(banco, 10, 0).sem_subtema = 2;
    banco.revisao = 3;
    abrir();

    expect(await screen.findByText(/2 questões não têm subtema/)).toBeInTheDocument();
    // As duas colunas carregam em requisições separadas.
    await waitFor(() =>
      expect(screen.getAllByText(/montada na revisão r0 e o banco está na r3/)).toHaveLength(2),
    );
  });

  it("banco aberto orienta a congelar", async () => {
    comBanco();
    abrir();

    expect(await screen.findByText(/Congele o banco na mesa de curadoria/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar à mesa" })).toHaveAttribute(
      "href",
      "/sessoes/5/banco",
    );
  });
});

describe("Provas — montar (M6)", () => {
  it("o formulário vem com o padrão e informa o que o banco tem", async () => {
    comBanco({ objetivas: 12, discursivas: 2, estado: "congelado" });
    abrir();

    expect(
      await screen.findByText("O banco v1 tem 12 objetivas e 2 discursivas ativas."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Objetivas por prova")).toHaveValue(10);
    expect(screen.getByLabelText("Discursivas por prova")).toHaveValue(0);
  });

  it("o padrão não passa das objetivas ativas", async () => {
    comBanco({ objetivas: 3, estado: "congelado" });
    abrir();

    expect(await screen.findByLabelText("Objetivas por prova")).toHaveValue(3);
  });

  it("soma fora de 1–25 bloqueia o envio", async () => {
    comBanco({ objetivas: 12, estado: "congelado" });
    const { user } = abrir();

    const campo = await screen.findByLabelText("Objetivas por prova");
    await user.clear(campo);
    await user.type(campo, "0");

    expect(screen.getByRole("button", { name: "Montar provas" })).toBeDisabled();
    expect(screen.getByText(/use de 1 a 25 questões/)).toBeInTheDocument();
  });

  it("montar pede confirmação e mostra as duas provas", async () => {
    const banco = comBanco({ objetivas: 15, estado: "congelado" });
    const { user } = abrir();

    await user.click(await screen.findByRole("button", { name: "Montar provas" }));
    expect(screen.getByText(/Montar as provas A e B com 10 questões cada\?/)).toBeInTheDocument();
    expect(banco.provas).toBeUndefined();
    await user.click(screen.getByRole("button", { name: "Confirmar montagem" }));

    expect(await prova("A")).toBeInTheDocument();
    expect(await prova("B")).toBeInTheDocument();
    expect(banco.provas?.revisao).toBe(0);
    expect(within(await item("A", 1)).getByText("Também na Prova B")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Montar provas" })).not.toBeInTheDocument();
  });

  it("insuficiência mostra a tabela do que o banco tem", async () => {
    const banco = comBanco({ objetivas: 3, estado: "congelado" });
    const { user } = abrir();

    const campo = await screen.findByLabelText("Objetivas por prova");
    await user.clear(campo);
    await user.type(campo, "5");
    await user.click(screen.getByRole("button", { name: "Montar provas" }));
    await user.click(screen.getByRole("button", { name: "Confirmar montagem" }));

    expect(await screen.findByText(/O banco não sustenta duas provas/)).toBeInTheDocument();
    expect(screen.getByText(/Cada prova pede 5 objetivas e 0 discursivas/)).toBeInTheDocument();
    const tabela = screen.getByRole("table", { name: "Questões ativas no banco" });
    // questaoFalsa: 1 → média, 2 → difícil, 3 → fácil.
    expect(within(tabela).getAllByRole("row")[1]).toHaveTextContent("Objetiva111");
    expect(banco.provas).toBeUndefined();
  });
});
