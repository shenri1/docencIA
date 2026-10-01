import { erroDeResposta } from "./erros";

describe("erroDeResposta", () => {
  it("usa detail e codigo das exceções de domínio e guarda os extras", () => {
    const erro = erroDeResposta(422, {
      detail: "pF + pM + pD deve somar exatamente 100%. Recebido soma 90.",
      codigo: "PARAMETROS_INCONSISTENTES",
      soma: 90,
    });

    expect(erro.status).toBe(422);
    expect(erro.codigo).toBe("PARAMETROS_INCONSISTENTES");
    expect(erro.message).toBe(
      "pF + pM + pD deve somar exatamente 100%. Recebido soma 90.",
    );
    expect(erro.extras).toEqual({ soma: 90 });
  });

  it("aceita HTTPException sem codigo", () => {
    const erro = erroDeResposta(404, { detail: "Not Found" });

    expect(erro.codigo).toBeUndefined();
    expect(erro.message).toBe("Not Found");
  });

  it("traduz o 422 de validação do Pydantic em erros por campo", () => {
    const erro = erroDeResposta(422, {
      detail: [
        {
          loc: ["body", "senha"],
          msg: "String should have at least 8 characters",
          type: "string_too_short",
          input: "[redacted]",
        },
        { loc: ["body", "nome"], msg: "Field required", type: "missing" },
      ],
    });

    expect(erro.campos).toEqual([
      { campo: "senha", mensagem: "String should have at least 8 characters" },
      { campo: "nome", mensagem: "Field required" },
    ]);
    expect(erro.message).toBe("Alguns campos não foram aceitos.");
  });

  it("cai numa mensagem por status quando o corpo não tem detail", () => {
    expect(erroDeResposta(500, null).message).toMatch(/erro interno/i);
    expect(erroDeResposta(502, "<html>").message).toMatch(/serviço/i);
    expect(erroDeResposta(418, undefined).message).toMatch(/418/);
  });
});
