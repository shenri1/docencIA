import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import type {
  Prompt,
  PromptCriar,
  RegistroAuditoria,
  TipoEventoAuditoria,
} from "../../api/tipos";

export const TAMANHO_PAGINA_LOGS = 50;

export interface FiltrosLog {
  tipo: TipoEventoAuditoria | "";
  /** Valor de `<input type="datetime-local">`, no fuso do navegador. */
  desde: string;
  ate: string;
  deslocamento: number;
}

const chaves = {
  prompts: ["admin", "prompts"] as const,
  logs: (filtros: FiltrosLog) => ["admin", "logs", filtros] as const,
};

const emIso = (local: string) => (local ? new Date(local).toISOString() : undefined);

export function usePrompts() {
  const cliente = useApi();
  return useQuery<Prompt[]>({
    queryKey: chaves.prompts,
    queryFn: () => desembrulhar(cliente.GET("/prompts")),
  });
}

/** Registrar não ativa: a versão nasce inativa. */
export function useRegistrarPrompt() {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Prompt, Error, PromptCriar>({
    mutationFn: (dados) => desembrulhar(cliente.POST("/prompts", { body: dados })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chaves.prompts }),
  });
}

export function useAtivarPrompt() {
  const cliente = useApi();
  const queryClient = useQueryClient();
  return useMutation<Prompt, Error, string>({
    mutationFn: (versao) =>
      desembrulhar(
        cliente.POST("/prompts/{versao}/ativar", { params: { path: { versao } } }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: chaves.prompts }),
  });
}

export function useLogs(filtros: FiltrosLog) {
  const cliente = useApi();
  return useQuery<RegistroAuditoria[]>({
    queryKey: chaves.logs(filtros),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/admin/logs", {
          params: {
            query: {
              tipo_evento: filtros.tipo || undefined,
              desde: emIso(filtros.desde),
              ate: emIso(filtros.ate),
              limite: TAMANHO_PAGINA_LOGS,
              deslocamento: filtros.deslocamento,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
