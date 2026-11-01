import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useApi } from "../../app/api-context";
import { type ClienteApi, desembrulhar, MENSAGEM_SEM_CONEXAO } from "../../api/cliente";
import { ErroApi, erroDeResposta } from "../../api/erros";
import type { Exportacao, Gabarito } from "../../api/tipos";
import { chavesBanco } from "../banco/curadoria";
import { chaves } from "../sessoes/api";

export type Modalidade = Gabarito["modalidade"];

export const chavesEntrega = {
  exportacoes: (bancoId: number) => [...chavesBanco.banco(bancoId), "exportacoes"] as const,
  gabarito: (provaId: number, modalidade: Modalidade) =>
    ["provas", provaId, "gabarito", modalidade] as const,
};

/** a modalidade é sempre explícita; o comentado só sai a pedido. */
export function useGabarito(provaId: number, modalidade: Modalidade) {
  const cliente = useApi();
  return useQuery<Gabarito>({
    queryKey: chavesEntrega.gabarito(provaId, modalidade),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/provas/{prova_id}/gabarito", {
          params: { path: { prova_id: provaId }, query: { modalidade } },
        }),
      ),
  });
}

export function useExportacoes(bancoId: number) {
  const cliente = useApi();
  return useQuery<Exportacao[]>({
    queryKey: chavesEntrega.exportacoes(bancoId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/bancos/{banco_id}/exportacoes", {
          params: { path: { banco_id: bancoId } },
        }),
      ),
  });
}

/** Mesma revisão exportada de novo devolve os mesmos registros (a API decide). */
export function useExportar(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Exportacao[], Error, void>({
    mutationFn: () =>
      desembrulhar(
        cliente.POST("/bancos/{banco_id}/exportacoes", {
          params: { path: { banco_id: bancoId } },
        }),
      ),
    // Dê certo ou não: o marco vai a `concluido`, ou a tela está velha.
    onSettled: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: chavesEntrega.exportacoes(bancoId) }),
        queryClient.invalidateQueries({ queryKey: chaves.marco(sessaoId) }),
      ]),
  });
}

const NOME_ARQUIVO = /filename="([^"]+)"/;

export function nomeDoArquivo(disposicao: string | null, id: number): string {
  return disposicao?.match(NOME_ARQUIVO)?.[1] ?? `exportacao-${id}.docx`;
}

/**
 * A rota exige token, então um <a href> para a API não serve. Baixa
 * por fetch e entrega por um link de blob, liberado logo depois do clique.
 */
export async function baixarExportacao(
  cliente: ClienteApi,
  exportacaoId: number,
): Promise<void> {
  let resultado;
  try {
    resultado = await cliente.GET("/exportacoes/{exportacao_id}/arquivo", {
      params: { path: { exportacao_id: exportacaoId } },
      parseAs: "blob",
    });
  } catch {
    throw new ErroApi(0, MENSAGEM_SEM_CONEXAO);
  }
  const { data, error, response } = resultado;
  if (!response.ok || !data) throw erroDeResposta(response.status, error);

  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = nomeDoArquivo(response.headers.get("content-disposition"), exportacaoId);
  link.click();
  URL.revokeObjectURL(url);
}
