import { render, screen } from "@testing-library/react";
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
