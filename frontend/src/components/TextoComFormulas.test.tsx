import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TextoComFormulas } from "./TextoComFormulas";

describe("TextoComFormulas", () => {
  it("formata fórmula válida", () => {
    const { container } = render(<TextoComFormulas texto={String.raw`Seja \(x^2\) o valor.`} />);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container).toHaveTextContent("Seja");
  });

  it("mostra a fórmula inválida crua, com o delimitador", () => {
    // O KaTeX aceita \color, que o validador recusa; aqui vale o que ele recusa.
    render(<TextoComFormulas texto={String.raw`Veja \(\frac{a}\) aqui.`} />);
    expect(screen.getByText(/\\\(\\frac\{a\}\\\)/)).toBeInTheDocument();
  });

  it("texto sem fórmula é o de antes", () => {
    const { container } = render(<TextoComFormulas texto={"O custo é R$ 50,00."} />);
    expect(container.querySelector(".katex")).toBeNull();
    expect(container).toHaveTextContent("O custo é R$ 50,00.");
  });

  it("href não vira link", () => {
    const { container } = render(<TextoComFormulas texto={String.raw`\(\href{http://x}{y}\)`} />);
    expect(container.querySelector("a")).toBeNull();
  });
});
