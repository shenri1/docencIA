import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { desembrulhar } from "../../api/cliente";
import type { ErroApi } from "../../api/erros";
import type { ResumoAuditoria } from "../../api/tipos";
import { useApi } from "../../app/api-context";
import { comoErroApi } from "../banco/api";
import { chavesBanco, consultaBanco, TAMANHO_BLOCO } from "../banco/curadoria";
import { chaves } from "../sessoes/api";

/** ~19 s por questão, então ~100 s por lote, abaixo dos dois timeouts. */
export const TAMANHO_LOTE = 5;

export const chaveAuditoria = (bancoId: number) =>
  [...chavesBanco.banco(bancoId), "auditoria"] as const;

/** Achados da revisão atual; banco nunca auditado devolve resumo vazio. */
export function useResumoAuditoria(bancoId: number) {
  const cliente = useApi();
  return useQuery<ResumoAuditoria>({
    queryKey: chaveAuditoria(bancoId),
    queryFn: () =>
      desembrulhar(
        cliente.GET("/bancos/{banco_id}/auditoria", {
          params: { path: { banco_id: bancoId } },
        }),
      ),
  });
}

/**
 * Todas as páginas do banco, com a mesma chave da mesa (cache compartilhado).
 * Os achados só trazem o número da questão; o enunciado vem daqui.
 */
export function useQuestoesDoBanco(bancoId: number, nAlvo: number) {
  const cliente = useApi();
  const paginas = Math.max(1, Math.ceil(nAlvo / TAMANHO_BLOCO));
  return useQueries({
    queries: Array.from({ length: paginas }, (_, i) => consultaBanco(cliente, bancoId, i + 1)),
    combine: (resultados) => ({
      questoes: resultados.flatMap((r) => r.data?.questoes ?? []),
      erro: resultados.find((r) => r.error)?.error ?? null,
    }),
  });
}

type Estado = "parado" | "auditando" | "pausando";

export interface Progresso {
  auditadas: number;
  total: number;
}

/**
 * Lotes de `TAMANHO_LOTE` em laço até as auditadas alcançarem o total,
 * ou até uma chamada não auditar nada novo (sem isso, um banco que mudou no meio
 * giraria para sempre). Cada questão é gravada sozinha: parar no meio não perde
 * nada. Erro interrompe o laço, e nada é reenviado sozinho.
 */
export function useAuditoriaEmLotes(bancoId: number, sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState<Estado>("parado");
  const [progresso, setProgresso] = useState<Progresso | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const pausaPedida = useRef(false);

  async function auditar(total: number, jaAuditadas: number) {
    pausaPedida.current = false;
    setErro(null);
    setEstado("auditando");
    setProgresso({ auditadas: jaAuditadas, total });
    try {
      for (;;) {
        const resumo = await desembrulhar(
          cliente.POST("/bancos/{banco_id}/auditoria", {
            params: { path: { banco_id: bancoId }, query: { limite: TAMANHO_LOTE } },
          }),
        );
        setProgresso({ auditadas: resumo.auditadas, total });
        // Os achados aparecem enquanto o laço ainda roda.
        queryClient.setQueryData(chaveAuditoria(bancoId), resumo);
        const nadaNovo = resumo.auditadas === resumo.ja_auditadas;
        if (resumo.auditadas >= total || nadaNovo || pausaPedida.current) break;
      }
    } catch (e) {
      setErro(comoErroApi(e));
    } finally {
      setEstado("parado");
      // O marco é quem diz quantas objetivas estão auditadas nesta revisão.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: chaves.marco(sessaoId) }),
        queryClient.invalidateQueries({ queryKey: chaveAuditoria(bancoId) }),
      ]);
    }
  }

  function pausar() {
    pausaPedida.current = true;
    setEstado("pausando");
  }

  return { estado, progresso, erro, auditar, pausar };
}
