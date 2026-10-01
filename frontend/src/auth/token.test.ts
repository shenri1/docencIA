import { guardarToken, lerToken, limparToken } from "./token";

describe("token", () => {
  it("devolve null quando não há token", () => {
    expect(lerToken()).toBeNull();
  });

  it("guarda e lê o token na sessionStorage", () => {
    guardarToken("abc");

    expect(lerToken()).toBe("abc");
    expect(sessionStorage.getItem("docencia.token")).toBe("abc");
  });

  it("limpa o token", () => {
    guardarToken("abc");
    limparToken();

    expect(lerToken()).toBeNull();
  });

  it("não quebra quando a sessionStorage está bloqueada", () => {
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("bloqueada");
    };
    try {
      expect(lerToken()).toBeNull();
    } finally {
      Storage.prototype.getItem = original;
    }
  });
});
