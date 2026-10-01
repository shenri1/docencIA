import type { MarcoBanco, MarcoSessao } from "../../api/tipos";
import { proximaAcao } from "./proximaAcao";

function banco(marco: MarcoBanco["marco"], banco_id = 1): MarcoBanco {
  return {
    versao: "v1",
    banco_id,
    revisao: 0,
    marco,
    motivo: null,
    n_alvo: 10,
    n_atual: 10,
    lacunas: 0,
    alerta_desvio: false,
    objetivas_ativas: 10,
    objetivas_auditadas: 0,
    comandos: [],
    campos_prosseguir: [],
  };
}

function marcoDaSessao(
  marco: MarcoSessao["marco"],
  bancos: MarcoBanco[] = [],
): MarcoSessao {
  return {
    sessao_id: 1,
    marco,
    n_materiais: 0,
    comandos: [],
    campos_prosseguir: [],
    bancos,
  };
}

describe("proximaAcao", () => {
  it("M1: enviar materiais", () => {
    expect(proximaAcao(marcoDaSessao("m1_materiais"))).toBe("Enviar materiais");
  });

  it("M2 sem banco: gerar banco", () => {
    expect(proximaAcao(marcoDaSessao("m2_banco"))).toBe("Gerar banco");
  });

  it.each([
    ["m3_exclusoes", "Revisar banco"],
    ["m6_provas", "Montar provas"],
    ["m10_docx", "Exportar provas"],
    ["concluido", "Ver exportações"],
    ["bloqueado", "Ver pendência"],
  ] as const)("banco em %s: %s", (marcoDoBanco, rotulo) => {
    expect(proximaAcao(marcoDaSessao("m2_banco", [banco(marcoDoBanco)]))).toBe(
      rotulo,
    );
  });

  it("com vários bancos usa o mais recente", () => {
    const bancos = [banco("concluido", 1), banco("m3_exclusoes", 2)];
    expect(proximaAcao(marcoDaSessao("m2_banco", bancos))).toBe("Revisar banco");
  });
});
