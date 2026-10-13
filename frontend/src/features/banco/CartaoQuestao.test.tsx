import { render, screen, within } from "@testing-library/react";
import { umaOrientacao, umaQuestao } from "../../test/fixtures";
import { CartaoQuestao } from "./CartaoQuestao";

describe("CartaoQuestao", () => {
  it("objetiva: enunciado, metadados, correta marcada e fontes", () => {
    render(<CartaoQuestao questao={umaQuestao()} />);

    const cartao = screen.getByRole("article", { name: "Questão 1" });
    expect(within(cartao).getByText("Qual é o papel do pivô no quicksort?")).toBeInTheDocument();
    expect(within(cartao).getByText("Objetiva")).toBeInTheDocument();
    expect(within(cartao).getByText("Média")).toBeInTheDocument();
    // o enum diz `entender`, a interface diz "Compreender".
    expect(within(cartao).getByText("Compreender")).toBeInTheDocument();
    expect(within(cartao).getByText("Ativa")).toBeInTheDocument();

    const correta = within(cartao).getByText("Particionar o vetor em menores e maiores").closest("li")!;
    expect(within(correta).getByText("Correta")).toBeInTheDocument();
    expect(within(cartao).getAllByText("Correta")).toHaveLength(1);

    expect(within(cartao).getByText(/O quicksort escolhe um pivô/)).toBeInTheDocument();
    expect(within(cartao).getByText(/slide 4/)).toBeInTheDocument();
  });

  it("discursiva: aspectos esperados com a fonte de cada um, sem alternativas", () => {
    render(
      <CartaoQuestao
        questao={umaQuestao({
          tipo: "discursiva",
          alternativas: [],
          letra_correta: null,
          aspectos_esperados: [
            {
              ordem: 1,
              texto: "Explica a escolha do pivô",
              fonte: { identificador_material: "P1", localizacao: "página 7", trecho_base: "A escolha do pivô define o custo." },
            },
          ],
        })}
      />,
    );

    const cartao = screen.getByRole("article", { name: "Questão 1" });
    expect(within(cartao).getByText("Discursiva")).toBeInTheDocument();
    expect(within(cartao).getByText(/Explica a escolha do pivô/)).toBeInTheDocument();
    expect(within(cartao).getByText(/A escolha do pivô define o custo/)).toBeInTheDocument();
    expect(within(cartao).queryByText("Correta")).not.toBeInTheDocument();
  });

  it("mostra as violações de forma que sobraram, como aviso", () => {
    render(
      <CartaoQuestao
        questao={umaQuestao({
          violacoes: [{ regra: "correta_longa", alvo: "B", detalhe: "A correta tem o dobro do tamanho da média." }],
        })}
      />,
    );

    expect(screen.getByText(/A correta tem o dobro do tamanho da média/)).toBeInTheDocument();
  });

  it("marcada para exclusão troca o estado exibido; candidata tem outro nome", () => {
    const { rerender } = render(<CartaoQuestao questao={umaQuestao()} marcada />);
    expect(screen.getByText("Marcada para exclusão")).toBeInTheDocument();
    expect(screen.queryByText("Ativa")).not.toBeInTheDocument();

    rerender(<CartaoQuestao questao={umaQuestao({ estado: "candidata" })} />);
    expect(
      screen.getByRole("article", { name: "Variação proposta para a questão 1" }),
    ).toBeInTheDocument();
  });

  it("mostra o rótulo dos formatos montados e nenhum na proposição", () => {
    const { rerender } = render(<CartaoQuestao questao={umaQuestao({ formato: "afirmativas" })} />);
    expect(screen.getByText("Afirmativas")).toBeInTheDocument();
    rerender(<CartaoQuestao questao={umaQuestao({ formato: "assercao_razao" })} />);
    expect(screen.getByText("Asserção-razão")).toBeInTheDocument();
    rerender(<CartaoQuestao questao={umaQuestao({ formato: "proposicao" })} />);
    expect(screen.queryByText("Afirmativas")).not.toBeInTheDocument();
    expect(screen.queryByText("Asserção-razão")).not.toBeInTheDocument();
  });

  it("mostra as orientações que geraram a questão", () => {
    render(
      <CartaoQuestao
        questao={umaQuestao()}
        orientacoes={[
          umaOrientacao({ id: 1, o_que_mudar: "exemplos práticos" }),
          umaOrientacao({ id: 2, o_que_mudar: null, cruzar_com: "memória cache" }),
        ]}
      />,
    );
    expect(
      screen.getByText("Orientações: Mudar: exemplos práticos; Articular com: memória cache"),
    ).toBeInTheDocument();
  });

  it("sem orientações não mostra a linha", () => {
    render(<CartaoQuestao questao={umaQuestao()} orientacoes={[]} />);
    expect(screen.queryByText(/Orientações:/)).not.toBeInTheDocument();
  });
});
