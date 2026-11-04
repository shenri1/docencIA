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
    // Prova não diz qual é a correta.
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
  const caixa = (numero: number, versao: "A" | "B") =>
    screen.getByRole("checkbox", { name: `Questão ${numero} na Prova ${versao}` });

  it("lista as questões ativas com uma caixa para cada prova", async () => {
    comBanco({ objetivas: 12, discursivas: 2, estado: "congelado" });
    abrir();

    expect(
      await screen.findByText("O banco v1 tem 12 objetivas e 2 discursivas ativas."),
    ).toBeInTheDocument();
    expect(await screen.findByRole("checkbox", { name: "Questão 14 na Prova B" })).not.toBeChecked();
    expect(caixa(1, "A")).not.toBeChecked();
    expect(screen.getByText("Enunciado da questão 1.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Montar provas" })).toBeDisabled();
  });

  it("sugerir seleção marca as caixas, e o docente ajusta", async () => {
    comBanco({ objetivas: 25, estado: "congelado" });
    const { user } = abrir();

    await user.click(await screen.findByRole("button", { name: "Sugerir seleção" }));

    await waitFor(() => expect(caixa(1, "A")).toBeChecked());
    expect(caixa(11, "B")).toBeChecked();
    expect(caixa(21, "A")).not.toBeChecked();
    expect(screen.getByText(/^Prova A: 10 questões/)).toBeInTheDocument();

    await user.click(caixa(21, "A"));
    expect(screen.getByText(/^Prova A: 11 questões/)).toBeInTheDocument();
  });

  it("resumo mostra tipo, faixa e as questões em comum", async () => {
    comBanco({ objetivas: 12, estado: "congelado" });
    const { user } = abrir();

    // questaoFalsa: 1 → média, 2 → difícil, 3 → fácil.
    await user.click(await screen.findByRole("checkbox", { name: "Questão 1 na Prova A" }));
    await user.click(caixa(3, "A"));
    await user.click(caixa(3, "B"));

    expect(
      screen.getByText("Prova A: 2 questões (2 objetivas, 0 discursivas) · fácil 1 · média 1 · difícil 0"),
    ).toBeInTheDocument();
    expect(screen.getByText("1 questão nas duas provas.")).toBeInTheDocument();
  });

  it("montar envia exatamente o que foi marcado", async () => {
    const banco = comBanco({ objetivas: 12, estado: "congelado" });
    const { user } = abrir();

    await user.click(await screen.findByRole("checkbox", { name: "Questão 1 na Prova A" }));
    await user.click(caixa(2, "A"));
    await user.click(caixa(2, "B"));
    await user.click(caixa(3, "B"));
    await user.click(screen.getByRole("button", { name: "Montar provas" }));

    expect(
      screen.getByText(/Montar a Prova A com 2 questões e a Prova B com 2 questões\?/),
    ).toBeInTheDocument();
    expect(banco.provas).toBeUndefined();
    await user.click(screen.getByRole("button", { name: "Confirmar montagem" }));

    expect(await prova("A")).toBeInTheDocument();
    expect(banco.provas?.a.map((q) => q.numero)).toEqual([1, 2]);
    expect(banco.provas?.b.map((q) => q.numero)).toEqual([2, 3]);
    expect(within(await item("A", 2)).getByText("Também na Prova B")).toBeInTheDocument();
  });

  it("sugestão que o banco não sustenta mostra a tabela do que ele tem", async () => {
    comBanco({ objetivas: 3, estado: "congelado" });
    const { user } = abrir();

    const campo = await screen.findByLabelText("Objetivas por prova");
    await user.clear(campo);
    await user.type(campo, "5");
    await user.click(screen.getByRole("button", { name: "Sugerir seleção" }));

    expect(await screen.findByText(/O banco não sustenta duas provas/)).toBeInTheDocument();
    const tabela = screen.getByRole("table", { name: "Questões ativas no banco" });
    expect(within(tabela).getAllByRole("row")[1]).toHaveTextContent("Objetiva111");
  });
});
