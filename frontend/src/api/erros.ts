/**
 * Erro devolvido pela API, já normalizado. Três formas chegam do servidor:
 * exceção de domínio ({detail, codigo, ...extras}), HTTPException ({detail})
 * e o 422 de validação do Pydantic ({detail: [{loc, msg}]}).
 */
export interface ErroDeCampo {
  campo: string;
  mensagem: string;
}

export class ErroApi extends Error {
  constructor(
    readonly status: number,
    mensagem: string,
    readonly codigo?: string,
    readonly extras: Record<string, unknown> = {},
    readonly campos?: ErroDeCampo[],
  ) {
    super(mensagem);
    this.name = "ErroApi";
  }
}

const MENSAGEM_POR_STATUS: Record<number, string> = {
  500: "Ocorreu um erro interno no servidor. Tente de novo em instantes.",
  502: "Um serviço do sistema não respondeu como esperado. Tente de novo.",
  503: "O sistema está indisponível ou ocupado. Tente de novo em instantes.",
};

function mensagemPadrao(status: number): string {
  return MENSAGEM_POR_STATUS[status] ?? `A requisição falhou (status ${status}).`;
}

function ehRegistro(valor: unknown): valor is Record<string, unknown> {
  return typeof valor === "object" && valor !== null && !Array.isArray(valor);
}

function camposDoPydantic(detail: unknown[]): ErroDeCampo[] {
  return detail.filter(ehRegistro).map((item) => {
    const loc = Array.isArray(item.loc) ? item.loc : [];
    return {
      campo: String(loc[loc.length - 1] ?? ""),
      mensagem: String(item.msg ?? ""),
    };
  });
}

export function erroDeResposta(status: number, corpo: unknown): ErroApi {
  if (!ehRegistro(corpo)) return new ErroApi(status, mensagemPadrao(status));

  const { detail, codigo, ...extras } = corpo;
  if (Array.isArray(detail)) {
    return new ErroApi(
      status,
      "Alguns campos não foram aceitos.",
      undefined,
      {},
      camposDoPydantic(detail),
    );
  }
  if (typeof detail === "string") {
    return new ErroApi(
      status,
      detail,
      typeof codigo === "string" ? codigo : undefined,
      extras,
    );
  }
  return new ErroApi(status, mensagemPadrao(status));
}
