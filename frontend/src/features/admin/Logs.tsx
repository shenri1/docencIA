import { useState } from "react";
import type { TipoEventoAuditoria } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo, CampoSelecao } from "../../components/Campo";
import { type FiltrosLog, TAMANHO_PAGINA_LOGS, useLogs } from "./api";

// Record fecha a lista: um tipo novo no contrato quebra a compilação aqui.
const ROTULO_EVENTO: Record<TipoEventoAuditoria, string> = {
  questao_gerada: "Questão gerada",
  exclusao: "Exclusão",
  congelamento: "Congelamento",
  substituicao_aceita: "Substituição aceita",
  substituicao_rejeitada: "Substituição rejeitada",
  provas_montadas: "Provas montadas",
  exportacao_docx: "Exportação DOCX",
  fallback_provedor: "Troca de provedor (fallback)",
  falha_provedor: "Falha de provedor",
  auditoria_questao: "Auditoria de questão",
  login_falho: "Login falho",
  token_suspeito: "Token suspeito",
  acesso_negado: "Acesso negado",
};

const rotuloDe = (tipo: string) =>
  ROTULO_EVENTO[tipo as TipoEventoAuditoria] ?? tipo;

const data = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "medium" });

export function Logs() {
  const [filtros, setFiltros] = useState<FiltrosLog>({
    tipo: "",
    desde: "",
    ate: "",
    deslocamento: 0,
  });
  const logs = useLogs(filtros);
  // Filtro novo volta à primeira página.
  const filtrar = (mudanca: Partial<FiltrosLog>) =>
    setFiltros((atual) => ({ ...atual, ...mudanca, deslocamento: 0 }));
  const paginar = (deslocamento: number) =>
    setFiltros((atual) => ({ ...atual, deslocamento }));

  const eventos = logs.data ?? [];
  const temSeguintes = eventos.length === TAMANHO_PAGINA_LOGS;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="font-serifa text-subtitulo">Log de auditoria</h2>
        <p className="font-grotesca text-detalhe text-texto-suave">
          Eventos críticos, do mais recente ao mais antigo. O ator aparece
          como pseudônimo: o log nunca guarda nome nem credencial.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <CampoSelecao
          rotulo="Tipo de evento"
          value={filtros.tipo}
          onChange={(e) => filtrar({ tipo: e.target.value as FiltrosLog["tipo"] })}
        >
          <option value="">Todos</option>
          {(Object.keys(ROTULO_EVENTO) as TipoEventoAuditoria[]).map((tipo) => (
            <option key={tipo} value={tipo}>
              {ROTULO_EVENTO[tipo]}
            </option>
          ))}
        </CampoSelecao>
        <Campo
          rotulo="Desde"
          type="datetime-local"
          value={filtros.desde}
          onChange={(e) => filtrar({ desde: e.target.value })}
        />
        <Campo
          rotulo="Até"
          type="datetime-local"
          value={filtros.ate}
          onChange={(e) => filtrar({ ate: e.target.value })}
        />
      </div>

      {logs.isError && <Alerta variante="erro">{logs.error.message}</Alerta>}
      {logs.isPending && (
        <p className="font-grotesca text-detalhe text-texto-suave">Carregando eventos…</p>
      )}
      {logs.data && eventos.length === 0 && (
        <p className="font-grotesca text-detalhe text-texto-suave">
          Nenhum evento encontrado.
        </p>
      )}

      {eventos.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse font-grotesca text-detalhe">
            <thead>
              <tr className="border-b border-borda text-left">
                <th className="py-2 pr-4 font-semibold">Quando</th>
                <th className="py-2 pr-4 font-semibold">Evento</th>
                <th className="py-2 pr-4 font-semibold">Entidade</th>
                <th className="py-2 pr-4 font-semibold">Ator</th>
                <th className="py-2 font-semibold">Detalhes</th>
              </tr>
            </thead>
            <tbody>
              {eventos.map((evento) => (
                <tr key={evento.id} className="border-b border-borda align-top">
                  <td className="tabular py-2 pr-4 whitespace-nowrap">
                    {data.format(new Date(evento.timestamp))}
                  </td>
                  <td className="py-2 pr-4">{rotuloDe(evento.tipo_evento)}</td>
                  <td className="tabular py-2 pr-4">{evento.entidade_afetada}</td>
                  <td className="tabular py-2 pr-4" title={evento.ator ?? undefined}>
                    {evento.ator ? `${evento.ator.slice(0, 10)}…` : "—"}
                  </td>
                  <td className="py-2">
                    <details>
                      <summary className="cursor-pointer">Ver</summary>
                      <pre className="mt-1 whitespace-pre-wrap break-words">
                        {JSON.stringify(evento.payload, null, 2)}
                      </pre>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex justify-between">
        <Botao
          variante="fantasma"
          disabled={filtros.deslocamento === 0}
          onClick={() =>
            paginar(Math.max(0, filtros.deslocamento - TAMANHO_PAGINA_LOGS))
          }
        >
          Anteriores
        </Botao>
        <Botao
          variante="fantasma"
          disabled={!temSeguintes}
          onClick={() => paginar(filtros.deslocamento + TAMANHO_PAGINA_LOGS)}
        >
          Seguintes
        </Botao>
      </div>
    </div>
  );
}
