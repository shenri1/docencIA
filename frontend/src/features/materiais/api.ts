import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import type { Indice, Material, TipoMaterial } from "../../api/tipos";
import { chaves as chavesSessao, useMarcoSessao } from "../sessoes/api";
import { rotaDoMarco } from "../sessoes/marco";

const chaveIndice = (sessaoId: number) =>
  ["sessoes", sessaoId, "indice"] as const;

export function useIndice(sessaoId: number) {
  const cliente = useApi();
  return useQuery<Indice>({
    queryKey: chaveIndice(sessaoId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/sessoes/{sessao_id}/materiais/indice", {
          params: { path: { sessao_id: sessaoId } },
        }),
      ),
  });
}

interface Envio {
  tipo: TipoMaterial;
  arquivo: File;
}

/** Um upload por requisição, multipart, como a API espera. */
export function useEnviarMaterial(sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Material, Error, Envio>({
    mutationFn: ({ tipo, arquivo }) =>
      desembrulhar(
        cliente.POST("/sessoes/{sessao_id}/materiais", {
          params: { path: { sessao_id: sessaoId } },
          // O schema gerado tipa o arquivo como string; o corpo real é multipart.
          body: { tipo, arquivo: "" },
          bodySerializer: () => {
            const form = new FormData();
            form.append("tipo", tipo);
            form.append("arquivo", arquivo, arquivo.name);
            return form;
          },
        }),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: chaveIndice(sessaoId) }),
  });
}

export function useRemoverMaterial(sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<unknown, Error, number>({
    mutationFn: (materialId) =>
      desembrulhar(
        cliente.DELETE("/sessoes/{sessao_id}/materiais/{material_id}", {
          params: { path: { sessao_id: sessaoId, material_id: materialId } },
        }),
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: chaveIndice(sessaoId) }),
  });
}

/** Indexa tudo (embeddings) antes de promover a sessão: pode demorar. */
export function useConfirmarIndice(sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Indice, Error, void>({
    mutationFn: () =>
      desembrulhar(
        cliente.POST("/sessoes/{sessao_id}/materiais/confirmar", {
          params: { path: { sessao_id: sessaoId } },
        }),
      ),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: chaveIndice(sessaoId) }),
        queryClient.invalidateQueries({ queryKey: chavesSessao.marco(sessaoId) }),
        queryClient.invalidateQueries({ queryKey: ["sessoes"], exact: false }),
      ]),
  });
}

/**
 * Materiais e índice só existem no M1. Se o servidor diz que a sessão já passou
 * dele (índice confirmado, página recarregada, outra máquina), a tela cede.
 */
export function useSairDoM1SeJaConfirmado(sessaoId: number) {
  const navigate = useNavigate();
  const marco = useMarcoSessao(sessaoId);
  useEffect(() => {
    if (marco.data && marco.data.marco !== "m1_materiais") {
      void navigate({
        to: rotaDoMarco(marco.data),
        params: { sessaoId: String(sessaoId) },
        replace: true,
      });
    }
  }, [marco.data, navigate, sessaoId]);
}
