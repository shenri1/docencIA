import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../app/api-context";
import { type ClienteApi, desembrulhar } from "../../api/cliente";
import { ErroApi } from "../../api/erros";
import type {
  Banco,
  DirecaoVariacao,
  PropostaSubstituicao,
  RelatorioImpacto,
} from "../../api/tipos";
import { chavesOrientacoes } from "../orientacoes/api";
import { chaves } from "../sessoes/api";

/** o banco é lido em blocos de 20. */
export const TAMANHO_BLOCO = 20;

export const chavesBanco = {
  banco: (bancoId: number) => ["bancos", bancoId] as const,
  proposta: (bancoId: number) => ["bancos", bancoId, "proposta"] as const,
};

/**
 * Sempre com gabarito e com histórico: a mesa precisa da correta, e é pelo
 * histórico que reencontra a candidata pendente depois de recarregar.
 * Separada de `useBanco` para a tela de auditoria ler as mesmas páginas, com a
 * mesma chave, sem repetir a consulta.
 */
export function consultaBanco(cliente: ClienteApi, bancoId: number, pagina: number) {
  return {
    queryKey: [...chavesBanco.banco(bancoId), pagina] as const,
    queryFn: () =>
      desembrulhar(
        cliente.GET("/bancos/{banco_id}", {
          params: {
            path: { banco_id: bancoId },
            query: {
              de: (pagina - 1) * TAMANHO_BLOCO + 1,
              ate: pagina * TAMANHO_BLOCO,
              com_gabarito: true,
              incluir_historico: true,
            },
          },
        }),
      ),
  };
}

export function useBanco(bancoId: number, pagina: number) {
  const cliente = useApi();
  return useQuery<Banco>({
    ...consultaBanco(cliente, bancoId, pagina),
    placeholderData: keepPreviousData,
  });
}

/**
 * Toda ação recarrega banco e marco, dê certo ou não: um 409 quer dizer que o
 * que está na tela é velho.
 */
export function useRecarregar(bancoId: number, sessaoId: number) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: chavesBanco.banco(bancoId) }),
      queryClient.invalidateQueries({ queryKey: chaves.marco(sessaoId) }),
    ]);
}

/** o 409 de revisão é orientação, não falha. */
export function mensagemDeErro(erro: Error): string {
  if (!(erro instanceof ErroApi)) return erro.message;
  if (erro.codigo === "REVISAO_DESATUALIZADA") {
    return "O banco mudou desde que você o viu. Confira e aplique de novo.";
  }
  if (erro.codigo === "LIMITE_ORIENTACOES") {
    return "A sessão já tem o máximo de orientações ativas: 5, das quais até 2 com articulação. Desative uma no painel de orientações antes de acrescentar outra.";
  }
  return erro.message;
}

export function useExcluir(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const recarregar = useRecarregar(bancoId, sessaoId);
  return useMutation<
    RelatorioImpacto,
    Error,
    { numeros: number[]; revisao_esperada: number }
  >({
    mutationFn: (body) =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/exclusoes", {
          params: { path: { banco_id: bancoId } },
          body,
        }),
      ),
    onSettled: recarregar,
  });
}

export interface PedidoVariacao {
  numero: number;
  /** Sem direção, a API recebe o pedido sem corpo e se comporta como antes. */
  direcao?: DirecaoVariacao;
}

/**
 * ~38 s de geração + revisão numa chamada só. A chave de mutação deixa a mesa
 * saber que há um pedido em curso e segurar os outros.
 */
export function usePedirVariacao(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  const recarregar = useRecarregar(bancoId, sessaoId);
  return useMutation<PropostaSubstituicao, Error, PedidoVariacao>({
    mutationKey: chavesBanco.proposta(bancoId),
    mutationFn: ({ numero, direcao }) =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/questoes/{numero}/substituicao", {
          params: { path: { banco_id: bancoId, numero } },
          body: direcao,
        }),
      ),
    // A variação guiada grava uma orientação: a lista da sessão também muda.
    onSettled: () =>
      Promise.all([
        recarregar(),
        queryClient.invalidateQueries({ queryKey: chavesOrientacoes.daSessao(sessaoId) }),
      ]),
  });
}

export function useAceitarVariacao(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const recarregar = useRecarregar(bancoId, sessaoId);
  return useMutation<RelatorioImpacto, Error, { numero: number; revisao_esperada: number }>({
    mutationFn: ({ numero, revisao_esperada }) =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/questoes/{numero}/substituicao/aceitar", {
          params: { path: { banco_id: bancoId, numero } },
          body: { revisao_esperada },
        }),
      ),
    onSettled: recarregar,
  });
}

export function useRejeitarVariacao(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const recarregar = useRecarregar(bancoId, sessaoId);
  return useMutation<unknown, Error, number>({
    mutationFn: (numero) =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/questoes/{numero}/substituicao/rejeitar", {
          params: { path: { banco_id: bancoId, numero } },
        }),
      ),
    onSettled: recarregar,
  });
}

/** A variável da mutação é a revisão que o docente estava vendo. */
export function useCongelar(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const recarregar = useRecarregar(bancoId, sessaoId);
  return useMutation<RelatorioImpacto, Error, number>({
    mutationFn: (revisao_esperada) =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/congelar", {
          params: { path: { banco_id: bancoId } },
          body: { revisao_esperada },
        }),
      ),
    onSettled: recarregar,
  });
}
