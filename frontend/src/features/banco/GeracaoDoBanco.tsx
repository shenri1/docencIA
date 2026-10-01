import { Link } from "@tanstack/react-router";
import { Alerta } from "../../components/Alerta";
import { proximaAcao } from "../sessoes/proximaAcao";
import { useMarcoSessao } from "../sessoes/api";

/**
 * Destino de todo marco depois do M1. A geração do banco (M2) e as telas
 * seguintes são as fases 2 a 6; por ora esta tela só informa onde a
 * sessão está, a partir do que o servidor diz.
 */
export function GeracaoDoBanco({ sessaoId }: { sessaoId: string }) {
  const marco = useMarcoSessao(Number(sessaoId));

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <h1 className="font-serifa text-titulo">Geração do banco</h1>

      {marco.isError && <Alerta variante="erro">{marco.error.message}</Alerta>}

      {marco.data && (
        <div className="cartao flex flex-col gap-3 p-6">
          <p className="font-serifa text-corpo-lg">
            O índice está confirmado, com {marco.data.n_materiais}{" "}
            {marco.data.n_materiais === 1 ? "material" : "materiais"}.
          </p>
          <p className="font-grotesca text-detalhe">
            Próxima ação: <span className="font-semibold">{proximaAcao(marco.data)}</span>
          </p>
          <p className="font-grotesca text-detalhe text-texto-suave">
            Esta etapa ainda não está disponível nesta versão da interface.
          </p>
        </div>
      )}

      <Link to="/" className="font-grotesca text-detalhe underline">
        Voltar às sessões
      </Link>
    </div>
  );
}
