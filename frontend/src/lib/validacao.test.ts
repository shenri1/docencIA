import { bytesUtf8, mensagemDeSenha, somaDosPercentuais } from "./validacao";

describe("bytesUtf8", () => {
  it("conta bytes, não caracteres", () => {
    expect(bytesUtf8("abc")).toBe(3);
    expect(bytesUtf8("ação")).toBe(6); // ç e ã ocupam 2 bytes cada
  });
});

describe("mensagemDeSenha", () => {
  it("aceita de 8 a 72 bytes", () => {
    expect(mensagemDeSenha("12345678")).toBeNull();
    expect(mensagemDeSenha("a".repeat(72))).toBeNull();
  });

  it("recusa menos de 8 bytes", () => {
    expect(mensagemDeSenha("1234567")).toMatch(/pelo menos 8/);
  });

  it("recusa mais de 72 bytes mesmo com menos de 72 caracteres", () => {
    const senha = "ç".repeat(40); // 40 caracteres, 80 bytes
    expect(senha.length).toBeLessThan(72);
    expect(mensagemDeSenha(senha)).toMatch(/72 bytes/);
  });
});

describe("somaDosPercentuais", () => {
  it("soma pF, pM e pD", () => {
    expect(somaDosPercentuais(10, 60, 30)).toBe(100);
    expect(somaDosPercentuais(10, 60, 20)).toBe(90);
  });
});
