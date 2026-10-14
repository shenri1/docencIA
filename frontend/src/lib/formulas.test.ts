import { describe, expect, it } from "vitest";
import casos from "../test/fixtures/notacao.json";
import { separar } from "./formulas";

describe("separar", () => {
  it.each(casos)("segue o fixture compartilhado: $nome", ({ texto, segmentos }) => {
    expect(separar(texto)).toEqual(segmentos);
  });
});
