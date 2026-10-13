import type { Orientacao } from "../api/tipos";
import {
  type BancoFalso,
  criarHandlers,
  novoEstado,
  questaoFalsa,
} from "../mocks/backendFalso";
import { server } from "../mocks/server";
import { DOCENTE, umMaterial, umaSessao } from "./fixtures";
import { API } from "./renderApp";

/** DOCENTE.id é 1, e o back-end falso reconhece o token "mock-token-<id>". */
export const TOKEN = "mock-token-1";

/**
 * Sessão 5 com o banco 7 já gerado, servida pelo back-end falso com estado.
 * O objeto devolvido é o estado vivo do banco: mudá-lo simula outra janela.
 */
export function comBanco({
  objetivas = 3,
  discursivas = 0,
  versao = "v1",
  estado: estadoBanco = "aberto",
  orientacoes = [],
}: {
  objetivas?: number;
  discursivas?: number;
  versao?: string;
  estado?: BancoFalso["estado"];
  orientacoes?: Orientacao[];
} = {}): BancoFalso {
  const estado = novoEstado();
  estado.docentes.push({ ...DOCENTE, senha: "segredo123" });
  const numeros = Array.from({ length: objetivas + discursivas }, (_, i) => i + 1);
  const banco: BancoFalso = {
    banco_id: 7,
    versao,
    n_objetivas: objetivas,
    n_discursivas: discursivas,
    gerados: new Set(numeros),
    recusados: new Set(),
    revisao: 0,
    estado: estadoBanco,
    questoes: numeros.map((n) => questaoFalsa(n, n > objetivas ? "discursiva" : "objetiva")),
    ultimo_relatorio: null,
  };
  estado.sessoes.push({
    ...umaSessao({ id: 5, estado: "banco_gerado" }),
    materiais: [umMaterial()],
    banco,
    orientacoes,
  });
  server.use(...criarHandlers(API, estado));
  return banco;
}
