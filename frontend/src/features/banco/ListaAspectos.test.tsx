import { render, screen } from "@testing-library/react";
import { ListaAspectos } from "./ListaAspectos";

describe("ListaAspectos", () => {
  it("com itens, mostra o título de cada item antes dos aspectos dele", () => {
    render(
      <ListaAspectos
        aspectos={[
          { ordem: 1, texto: "Explica as camadas", item: 1 },
          { ordem: 2, texto: "Avalia os pesos", item: 2 },
        ]}
        fonte={() => null}
      />,
    );
    const textos = screen.getAllByText(/Item [ab]\)|Explica|Avalia/).map((n) => n.textContent);
    expect(textos).toEqual(["Item a)", "1. Explica as camadas", "Item b)", "2. Avalia os pesos"]);
  });

  it("sem itens, nenhum título de item", () => {
    render(<ListaAspectos aspectos={[{ ordem: 1, texto: "Explica", item: null }]} fonte={() => null} />);
    expect(screen.queryByText(/Item a\)/)).not.toBeInTheDocument();
  });
});
