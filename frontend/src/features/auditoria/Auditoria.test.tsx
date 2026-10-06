import { screen, waitFor, within } from "@testing-library/react";
import { auditoriaFalsa, criarHandlers, novoEstado } from "../../mocks/backendFalso";
import { server } from "../../mocks/server";
import { DOCENTE, umAchado, umMaterial, umaSessao } from "../../test/fixtures";
import { comBanco } from "../../test/comBanco";
import { API, renderApp } from "../../test/renderApp";

// DOCENTE.id é 1, e o falso reconhece o token "mock-token-<id>".
const abrir = () => renderApp("/sessoes/5/auditoria", { token: "mock-token-1" });
const botao = (nome: string) => screen.findByRole("button", { name: nome });

describe("Auditoria — situação", () => {
  it("mostra quantas objetivas já foram auditadas nesta revisão", async () => {
    const banco = comBanco({ objetivas: 6 });
    banco.auditoria = auditoriaFalsa({
      feitas: new Map([
        [1, 0],
        [2, 0],
        [3, 0],
      ]),
    });
    abrir();

    expect(await screen.findByText("3 de 6 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(await botao("Continuar auditoria")).toBeEnabled();
  });

  it("sem nada auditado, o botão é Auditar objetivas", async () => {
    comBanco();
    abrir();

    expect(await screen.findByText("0 de 3 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(await botao("Auditar objetivas")).toBeEnabled();
  });

  it("banco sem objetivas ativas explica e não oferece auditar", async () => {
    comBanco({ objetivas: 0, discursivas: 2 });
    abrir();

    expect(await screen.findByText(/não tem objetivas ativas/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /uditar|uditoria/ })).not.toBeInTheDocument();
  });

  it("sessão sem banco manda gerar", async () => {
    const estado = novoEstado();
    estado.docentes.push({ ...DOCENTE, senha: "segredo123" });
    estado.sessoes.push({ ...umaSessao({ id: 5, estado: "materiais_confirmados" }), materiais: [umMaterial()] });
    server.use(...criarHandlers(API, estado));
    abrir();

    expect(await screen.findByRole("link", { name: "Gerar banco" })).toHaveAttribute(
      "href",
      "/sessoes/5/geracao",
    );
  });

  it("volta para a curadoria", async () => {
    comBanco();
    abrir();
    expect(await screen.findByRole("link", { name: "Voltar à curadoria" })).toHaveAttribute(
      "href",
      "/sessoes/5/banco",
    );
  });
});

describe("Auditoria — laço em lotes", () => {
  it("audita de 5 em 5 até alcançar o total", async () => {
    const banco = comBanco({ objetivas: 7 });
    const { user } = abrir();

    await user.click(await botao("Auditar objetivas"));

    expect(await screen.findByText("7 de 7 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(banco.auditoria?.limites).toEqual([5, 5]);
    expect(await botao("Auditoria completa")).toBeDisabled();
  });

  it("mostra o progresso enquanto audita", async () => {
    comBanco({ objetivas: 7 }).auditoria = auditoriaFalsa({ atraso: 80 });
    const { user } = abrir();

    await user.click(await botao("Auditar objetivas"));

    expect(await screen.findByText("0 de 7 objetivas auditadas")).toBeInTheDocument();
    expect(await screen.findByText("5 de 7 objetivas auditadas")).toBeInTheDocument();
    // Espera o laço terminar: um laço solto chamaria o handler do teste seguinte.
    expect(await screen.findByText("7 de 7 objetivas auditadas na revisão r0")).toBeInTheDocument();
  });

  it("pausar para depois do lote em curso e Continuar retoma", async () => {
    const banco = comBanco({ objetivas: 12 });
    banco.auditoria = auditoriaFalsa({ atraso: 80 });
    const { user } = abrir();

    await user.click(await botao("Auditar objetivas"));
    await screen.findByText("5 de 12 objetivas auditadas");
    await user.click(screen.getByRole("button", { name: "Pausar auditoria" }));

    expect(await screen.findByText("10 de 12 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(banco.auditoria.limites).toHaveLength(2);

    await user.click(await botao("Continuar auditoria"));
    expect(await screen.findByText("12 de 12 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(banco.auditoria.limites).toHaveLength(3);
  });

  it("erro no meio do laço mostra a mensagem, guarda o que foi feito e permite continuar", async () => {
    const banco = comBanco({ objetivas: 7 });
    banco.auditoria = auditoriaFalsa({ falhaNa: 2 });
    const { user } = abrir();

    await user.click(await botao("Auditar objetivas"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/não conseguiu usar/);
    expect(await screen.findByText("5 de 7 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(banco.auditoria.limites).toHaveLength(2);

    await user.click(await botao("Continuar auditoria"));
    expect(await screen.findByText("7 de 7 objetivas auditadas na revisão r0")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Auditoria — resultado", () => {
  it("mostra a proporção, as discursivas ignoradas e o achado com trecho e orientação", async () => {
    const banco = comBanco({ objetivas: 4, discursivas: 1 });
    banco.auditoria = auditoriaFalsa({
      achados: {
        2: [umAchado({ risco: "correta_nao_unica", alvo: "C", localizacao: "slide 4" })],
        3: [
          umAchado({
            risco: "assimetria_forma",
            alvo: "A",
            localizacao: null,
            trecho_fonte: null,
            proposta_ajuste: "A alternativa A é mais longa que as outras — encurte-a.",
          }),
        ],
      },
    });
    const { user } = abrir();

    await user.click(await botao("Auditar objetivas"));

    expect(
      await screen.findByText(/2 de 4 objetivas auditadas com achado \(50,00%\)/),
    ).toBeInTheDocument();
    expect(screen.getByText(/1 discursiva não foi auditada/)).toBeInTheDocument();

    const semantico = await screen.findByRole("region", { name: "Achados da questão 2" });
    expect(within(semantico).getByText("Mais de uma alternativa pode estar correta")).toBeInTheDocument();
    expect(within(semantico).getByText("Alternativa apontada: C")).toBeInTheDocument();
    expect(within(semantico).getByText(/slide 4/)).toBeInTheDocument();
    expect(within(semantico).getByText(/Reescreva a alternativa C/)).toBeInTheDocument();
    expect(within(semantico).getByText(/o sistema não executa/)).toBeInTheDocument();

    // O enunciado vem da leitura do banco, e a letra apontada é marcada no cartão.
    const cartao = screen.getByRole("article", { name: "Questão 2" });
    expect(within(cartao).getByText("Enunciado da questão 2.")).toBeInTheDocument();
    const letraC = within(cartao).getByText("Alternativa C da questão 2").closest("li")!;
    expect(within(letraC).getByText("Apontada pela auditoria")).toBeInTheDocument();

    // Achado de forma não tem trecho da fonte.
    const forma = screen.getByRole("region", { name: "Achados da questão 3" });
    expect(within(forma).getByText("Alternativa destoa em forma ou tamanho")).toBeInTheDocument();
    expect(within(forma).queryByText(/Trecho/)).not.toBeInTheDocument();

    // Questões sem achado não aparecem.
    expect(screen.queryByRole("region", { name: "Achados da questão 1" })).not.toBeInTheDocument();
  });

  it("sem achados, diz isso sem afirmar que o banco está bom", async () => {
    comBanco({ objetivas: 2 });
    const { user } = abrir();

    await user.click(await botao("Auditar objetivas"));

    expect(await screen.findByText(/Nenhum achado nas objetivas auditadas/)).toBeInTheDocument();
    expect(screen.getByText(/não garante que o banco esteja sem problemas/)).toBeInTheDocument();
  });

  it("recarregar mostra de novo os achados já gravados", async () => {
    const banco = comBanco({ objetivas: 3 });
    banco.auditoria = auditoriaFalsa({
      achados: { 1: [umAchado()] },
      feitas: new Map([
        [1, 0],
        [2, 0],
        [3, 0],
      ]),
    });
    abrir();

    expect(await screen.findByRole("region", { name: "Achados da questão 1" })).toBeInTheDocument();
    expect(await screen.findByText("Auditoria completa")).toBeDisabled();
  });

  it("um banco que mudou de revisão volta a pedir a auditoria", async () => {
    const banco = comBanco({ objetivas: 3 });
    banco.auditoria = auditoriaFalsa({
      feitas: new Map([
        [1, 0],
        [2, 0],
        [3, 0],
      ]),
    });
    banco.revisao = 1;
    abrir();

    await waitFor(() =>
      expect(screen.getByText("0 de 3 objetivas auditadas na revisão r1")).toBeInTheDocument(),
    );
    expect(await botao("Auditar objetivas")).toBeEnabled();
  });
});
