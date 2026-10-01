import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { Alerta } from "../../components/Alerta";
import { useMarcoSessao } from "./api";
import { rotaDoMarco } from "./marco";

/**
 * A rota da sessão não tem tela: pergunta o marco ao servidor e encaminha para
 * a tela dele. É o que faz recarregar a página, ou abrir em outra máquina,
 * cair no mesmo ponto.
 */
export function SessaoPorMarco({ sessaoId }: { sessaoId: string }) {
  const navigate = useNavigate();
  const marco = useMarcoSessao(Number(sessaoId));

  useEffect(() => {
    if (!marco.data) return;
    void navigate({ to: rotaDoMarco(marco.data), params: { sessaoId }, replace: true });
  }, [marco.data, navigate, sessaoId]);

  if (marco.isError) {
    return <Alerta variante="erro">{marco.error.message}</Alerta>;
  }
  return (
    <p className="font-grotesca text-detalhe text-texto-suave">
      Abrindo a sessão…
    </p>
  );
}
