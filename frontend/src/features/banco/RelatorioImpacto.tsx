import type { RelatorioImpacto as Relatorio } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { ROTULO_FAIXA } from "./rotulos";

const ROTULO_EVENTO: Record<Relatorio["evento"], string> = {
  exclusao: "exclusão",
  substituicao: "substituição",
  congelamento: "congelamento",
};

const FAIXAS = ["facil", "media", "dificil"] as const;

export function RelatorioImpacto({ relatorio }: { relatorio: Relatorio }) {
  return (
    <div className="flex flex-col gap-2 font-grotesca text-detalhe">
      <p className="tabular">
        {`Último relatório de impacto: ${ROTULO_EVENTO[relatorio.evento]} na revisão r${relatorio.revisao}, com ${relatorio.n_final} questões ativas.`}
      </p>
      <ul className="tabular">
        {Object.entries(relatorio.contagem_por_faixa).map(([tipo, contagem]) => (
          <li key={tipo}>
            {tipo === "discursiva" ? "Discursivas" : "Objetivas"}:{" "}
            {FAIXAS.map((f) => `${ROTULO_FAIXA[f].toLowerCase()} ${contagem[f] ?? 0}`).join(" · ")}
          </li>
        ))}
      </ul>
      {relatorio.alerta_desvio && (
        <Alerta variante="aviso">
          A distribuição por faixa se afastou mais de 5 pontos do pF/pM/pD pedido. É uma
          observação: a decisão é sua.
        </Alerta>
      )}
    </div>
  );
}
