import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { Alerta } from "../../components/Alerta";
import { useMarcoSessao } from "./api";

/**
 * A rota da sessão não tem tela: pergunta o marco ao servidor e encaminha para
 * a tela dele. É o que faz recarregar a página, ou abrir em outra máquina,
 * cair no mesmo ponto.
 */
export function SessaoPorMarco({ sessaoId }: { sessaoId: string }) {
  const navigate = useNavigate();
  const marco = useMarcoSessao(Number(sessaoId));
  const atual = marco.data?.marco;

  useEffect(() => {
    if (!atual) return;
    void navigate({
      to:
        atual === "m1_materiais"
          ? "/sessoes/$sessaoId/materiais"
          : "/sessoes/$sessaoId/banco",
      params: { sessaoId },
      replace: true,
    });
  }, [atual, navigate, sessaoId]);

  if (marco.isError) {
    return <Alerta variante="erro">{marco.error.message}</Alerta>;
  }
  return (
    <p className="font-grotesca text-detalhe text-texto-suave">
      Abrindo a sessão…
    </p>
  );
}
