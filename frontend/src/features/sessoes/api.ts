import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import type { MarcoSessao, Sessao, SessaoCriar } from "../../api/tipos";

export const TAMANHO_PAGINA = 20;

export const chaves = {
  sessoes: (pagina: number) => ["sessoes", pagina] as const,
  marco: (sessaoId: number) => ["sessoes", sessaoId, "marco"] as const,
};

/** `pagina` começa em 1; a API pagina por limit/offset e não devolve o total. */
export function useSessoes(pagina: number) {
  const cliente = useApi();
  return useQuery<Sessao[]>({
    queryKey: chaves.sessoes(pagina),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/sessoes", {
          params: {
            query: {
              limit: TAMANHO_PAGINA,
              offset: (pagina - 1) * TAMANHO_PAGINA,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function useCriarSessao() {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Sessao, Error, SessaoCriar>({
    mutationFn: (dados) =>
      desembrulhar(cliente.POST("/sessoes", { body: dados })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessoes"] }),
  });
}

/** O estado do fluxo mora no servidor: o front só pergunta o marco e renderiza. */
export function useMarcoSessao(sessaoId: number) {
  const cliente = useApi();
  return useQuery<MarcoSessao>({
    queryKey: chaves.marco(sessaoId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/sessoes/{sessao_id}/marco", {
          params: { path: { sessao_id: sessaoId } },
        }),
      ),
  });
}
