import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import type { Banco, Prova, ProvasMontadas } from "../../api/tipos";
import { chavesBanco } from "../banco/curadoria";
import { chaves } from "../sessoes/api";

export const chavesProvas = {
  doBanco: (bancoId: number) => [...chavesBanco.banco(bancoId), "provas"] as const,
  prova: (provaId: number) => ["provas", provaId] as const,
};

/**
 * O mesmo que a montagem devolveu, recalculado pela API. Só é usado
 * com o marco em M10 ou concluído — sem provas, a API responde 404.
 */
export function useProvasDoBanco(bancoId: number) {
  const cliente = useApi();
  return useQuery<ProvasMontadas>({
    queryKey: chavesProvas.doBanco(bancoId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/bancos/{banco_id}/provas", {
          params: { path: { banco_id: bancoId } },
        }),
      ),
  });
}

export function useProva(provaId: number) {
  const cliente = useApi();
  return useQuery<Prova>({
    queryKey: chavesProvas.prova(provaId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/provas/{prova_id}", { params: { path: { prova_id: provaId } } }),
      ),
  });
}

export function useMontarProvas(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<
    ProvasMontadas,
    Error,
    { numeros_a: number[]; numeros_b: number[]; revisao_esperada: number }
  >({
    mutationFn: (body) =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/provas", {
          params: { path: { banco_id: bancoId } },
          body,
        }),
      ),
    onSuccess: (montadas) =>
      queryClient.setQueryData(chavesProvas.doBanco(bancoId), montadas),
    // Dê certo ou não: um 409 diz que o que está na tela é velho.
    onSettled: () => queryClient.invalidateQueries({ queryKey: chaves.marco(sessaoId) }),
  });
}

/** Todas as questões do banco num pedido só: um banco tem no máximo 25. */
export function useQuestoesDoBanco(bancoId: number, ate: number) {
  const cliente = useApi();
  return useQuery<Banco>({
    queryKey: [...chavesProvas.doBanco(bancoId), "questoes", ate],
    queryFn: () =>
      desembrulhar(
        cliente.GET("/bancos/{banco_id}", {
          params: { path: { banco_id: bancoId }, query: { de: 1, ate } },
        }),
      ),
  });
}

/** A seleção automática, só leitura: preenche as caixas para o docente ajustar. */
export function useSugerirSelecao(bancoId: number) {
  const cliente = useApi();
  return useMutation<
    { numeros_a: number[]; numeros_b: number[] },
    Error,
    { n_objetivas: number; n_discursivas: number }
  >({
    mutationFn: (query) =>
      desembrulhar(
        cliente.GET("/bancos/{banco_id}/provas/sugestao", {
          params: { path: { banco_id: bancoId }, query },
        }),
      ),
  });
}
