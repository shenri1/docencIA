import { formatarPercentual, formatarTamanho, rotuloDePaginas } from "./formatar";

describe("formatarTamanho", () => {
  it.each([
    [0, "0 B"],
    [512, "512 B"],
    [2048, "2,0 KB"],
    [1_048_576, "1,0 MB"],
    [31_457_280, "30,0 MB"],
  ])("%d bytes -> %s", (bytes, texto) => {
    expect(formatarTamanho(bytes)).toBe(texto);
  });
});

describe("rotuloDePaginas", () => {
  it("usa slides para PPTX e páginas para o resto", () => {
    expect(rotuloDePaginas(24, "pptx")).toBe("24 slides");
    expect(rotuloDePaginas(10, "pdf")).toBe("10 páginas");
  });

  it("trata o singular", () => {
    expect(rotuloDePaginas(1, "pptx")).toBe("1 slide");
    expect(rotuloDePaginas(1, "docx")).toBe("1 página");
  });

  it("devolve null quando a API não informou", () => {
    expect(rotuloDePaginas(null, "txt")).toBeNull();
    expect(rotuloDePaginas(undefined, "txt")).toBeNull();
  });
});

describe("formatarPercentual", () => {
  it.each([
    ["0.00", "0,00"],
    ["25.00", "25,00"],
    ["33.33", "33,33"],
    ["100.00", "100,00"],
  ])("%s -> %s", (valor, texto) => {
    expect(formatarPercentual(valor)).toBe(texto);
  });
});
