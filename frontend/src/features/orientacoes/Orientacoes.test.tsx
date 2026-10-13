import { screen, waitFor, within } from "@testing-library/react";
import { comBanco } from "../../test/comBanco";
import { umaOrientacao } from "../../test/fixtures";
import { renderApp } from "../../test/renderApp";
import { textoOrientacao } from "./texto";

const abrirGeracao = () => renderApp("/sessoes/5/geracao", { token: "mock-token-1" });

describe("textoOrientacao", () => {
  it("combina articular e mudar como o pedido ao modelo", () => {
    expect(
      textoOrientacao({ cruzar_com: "memória cache", o_que_mudar: "enunciado curto" }),
    ).toBe("Articular com: memória cache. Mudar: enunciado curto");
    expect(textoOrientacao({ cruzar_com: null, o_que_mudar: "curto" })).toBe("Mudar: curto");
  });
});

describe("Painel de orientações", () => {
  it("acrescenta, mostra o contador e desativa", async () => {
    comBanco();
    const { user } = abrirGeracao();

    const painel = await screen.findByRole("region", { name: "Orientações da sessão" });
    expect(within(painel).getByText("Nenhuma orientação ativa.")).toBeInTheDocument();

    await user.type(within(painel).getByLabelText("Nova orientação"), "Prefiro enunciados curtos");
    await user.click(within(painel).getByRole("button", { name: "Acrescentar" }));

    const item = (await within(painel).findByText("Mudar: Prefiro enunciados curtos")).closest("li")!;
    expect(within(painel).getByText("1/5 · 0/2 com articulação")).toBeInTheDocument();
    expect(within(painel).getByLabelText("Nova orientação")).toHaveValue("");

    await user.click(within(item).getByRole("button", { name: "Desativar" }));
    await waitFor(() =>
      expect(within(painel).queryByText("Mudar: Prefiro enunciados curtos")).not.toBeInTheDocument(),
    );
    expect(within(painel).getByText("0/5 · 0/2 com articulação")).toBeInTheDocument();
  });

  it("no teto desabilita o acréscimo e diz o que fazer", async () => {
    comBanco({
      orientacoes: Array.from({ length: 5 }, (_, i) =>
        umaOrientacao({ id: i + 1, o_que_mudar: `orientação ${i + 1}` }),
      ),
    });
    const { user } = abrirGeracao();

    const painel = await screen.findByRole("region", { name: "Orientações da sessão" });
    await user.type(within(painel).getByLabelText("Nova orientação"), "mais uma");

    expect(within(painel).getByRole("button", { name: "Acrescentar" })).toBeDisabled();
    expect(
      within(painel).getByText("Desative uma orientação para acrescentar outra."),
    ).toBeInTheDocument();
  });

  it("não lista inativas nem pontuais", async () => {
    comBanco({
      orientacoes: [
        umaOrientacao({ id: 1, o_que_mudar: "vale" }),
        umaOrientacao({ id: 2, o_que_mudar: "desativada", estado: "inativa" }),
        umaOrientacao({
          id: 3,
          origem: "questao",
          estado: "pontual",
          o_que_mudar: "só de uma variação",
          banco_id: 7,
          numero_origem: 1,
        }),
      ],
    });
    abrirGeracao();

    const painel = await screen.findByRole("region", { name: "Orientações da sessão" });
    expect(await within(painel).findByText("Mudar: vale")).toBeInTheDocument();
    expect(within(painel).queryByText(/desativada/)).not.toBeInTheDocument();
    expect(within(painel).queryByText(/só de uma variação/)).not.toBeInTheDocument();
  });
});
