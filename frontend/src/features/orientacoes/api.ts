import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import type { Orientacao } from "../../api/tipos";

// Espelham backend/app/services/orientacoes/orientacao_service.py. Conveniência:
// a API continua sendo a autoridade (LIMITE_ORIENTACOES).
export const TETO_ATIVAS = 5;
export const TETO_CRUZAMENTOS = 2;

export const chavesOrientacoes = {
  daSessao: (sessaoId: number) => ["sessoes", sessaoId, "orientacoes"] as const,
  ultimaSessao: ["orientacoes", "ultima-sessao"] as const,
};

export function contar(orientacoes: readonly Orientacao[]) {
  const ativas = orientacoes.filter((o) => o.estado === "ativa");
  return { ativas: ativas.length, comCruzamento: ativas.filter((o) => o.cruzar_com).length };
}

export function useOrientacoes(sessaoId: number) {
  const cliente = useApi();
  return useQuery<Orientacao[]>({
    queryKey: chavesOrientacoes.daSessao(sessaoId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/sessoes/{sessao_id}/orientacoes", {
          params: { path: { sessao_id: sessaoId } },
        }),
      ),
  });
}

export function useCriarOrientacao(sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Orientacao, Error, string>({
    mutationFn: (o_que_mudar) =>
      desembrulhar(
        cliente.POST("/sessoes/{sessao_id}/orientacoes", {
          params: { path: { sessao_id: sessaoId } },
          body: { o_que_mudar },
        }),
      ),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: chavesOrientacoes.daSessao(sessaoId) }),
  });
}

export function useDesativarOrientacao(sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Orientacao, Error, number>({
    mutationFn: (orientacao_id) =>
      desembrulhar(
        cliente.POST("/sessoes/{sessao_id}/orientacoes/{orientacao_id}/desativar", {
          params: { path: { sessao_id: sessaoId, orientacao_id } },
        }),
      ),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: chavesOrientacoes.daSessao(sessaoId) }),
  });
}

/**
 * Pré-preenchimento da nova sessão: as orientações de sessão ativas da sessão
 * mais recente do docente. Sem perfil permanente — cada sessão continua com as
 * suas, e o docente edita antes de criar.
 */
export function useOrientacoesDaUltimaSessao() {
  const cliente = useApi();
  return useQuery<string[]>({
    queryKey: chavesOrientacoes.ultimaSessao,
    queryFn: async () => {
      const sessoes = await desembrulhar(
        cliente.GET("/sessoes", { params: { query: { limit: 20, offset: 0 } } }),
      );
      if (sessoes.length === 0) return [];
      // A API lista da mais recente para a mais antiga; o maior id não depende disso.
      const ultima = sessoes.reduce((a, b) => (b.id > a.id ? b : a));
      const orientacoes = await desembrulhar(
        cliente.GET("/sessoes/{sessao_id}/orientacoes", {
          params: { path: { sessao_id: ultima.id } },
        }),
      );
      return orientacoes
        .filter((o) => o.origem === "sessao" && o.estado === "ativa")
        .map((o) => o.o_que_mudar ?? "")
        .filter(Boolean);
    },
  });
}
