import { render, screen } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Botao } from "./Botao";

describe("Botao", () => {
  it("ignora o segundo clique enquanto o handler assíncrono não resolve", async () => {
    let resolver!: () => void;
    const aoClicar = vi.fn(() => new Promise<void>((r) => (resolver = r)));
    render(<Botao onClick={aoClicar}>Ir</Botao>);

    await userEvent.dblClick(screen.getByRole("button", { name: "Ir" }));
    expect(aoClicar).toHaveBeenCalledTimes(1);

    resolver();
    await vi.waitFor(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Ir" }));
      expect(aoClicar).toHaveBeenCalledTimes(2);
    });
  });

  it("ignora o duplo clique em handler síncrono", async () => {
    const aoClicar = vi.fn();
    render(<Botao onClick={aoClicar}>Ir</Botao>);

    await userEvent.dblClick(screen.getByRole("button", { name: "Ir" }));
    expect(aoClicar).toHaveBeenCalledTimes(1);
  });
});

describe("Botao com renderização no meio", () => {
  it("o handler que muda estado do pai não reabre a janela do duplo clique", async () => {
    const aoClicar = vi.fn();
    function Pai() {
      const [, setCliques] = useState(0);
      return (
        <Botao
          onClick={() => {
            aoClicar();
            setCliques((n) => n + 1); // re-renderiza o botão antes do segundo clique
          }}
        >
          Ir
        </Botao>
      );
    }
    render(<Pai />);

    await userEvent.dblClick(screen.getByRole("button"));
    expect(aoClicar).toHaveBeenCalledTimes(1);
  });
});

describe("Botao submit", () => {
  it("envia o formulário uma vez só no duplo clique", async () => {
    const aoEnviar = vi.fn((e: { preventDefault: () => void }) => e.preventDefault());
    render(
      <form onSubmit={aoEnviar}>
        <Botao type="submit">Enviar</Botao>
      </form>,
    );

    await userEvent.dblClick(screen.getByRole("button", { name: "Enviar" }));
    expect(aoEnviar).toHaveBeenCalledTimes(1);
  });
});
