import { Link } from "@tanstack/react-router";
import type { Marco } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { useProvasDoBanco } from "../provas/api";
import { useMarcoSessao } from "../sessoes/api";
import { bancoMaisRecente } from "../sessoes/marco";
import { Exportacao } from "./Exportacao";
import { Gabaritos } from "./Gabaritos";

// Gabarito e exportação existem do M10 em diante.
const COM_PROVAS: ReadonlySet<Marco> = new Set<Marco>(["m10_docx", "concluido"]);

/** gabaritos e DOCX do banco mais recente da sessão. */
export function Entrega({ sessaoId }: { sessaoId: string }) {
  const id = Number(sessaoId);
  const marco = useMarcoSessao(id);
  const marcoBanco = marco.data ? bancoMaisRecente(marco.data) : null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <h1 className="font-serifa text-titulo">Gabaritos e DOCX</h1>

      {marco.isError && <Alerta variante="erro">{marco.error.message}</Alerta>}
      {marco.data && marcoBanco === null && (
        <Alerta variante="aviso">Esta sessão ainda não tem banco.</Alerta>
      )}
      {marco.data &&
        marcoBanco &&
        (COM_PROVAS.has(marcoBanco.marco) ? (
          <ConteudoEntrega bancoId={marcoBanco.banco_id} sessaoId={id} />
        ) : (
          <Alerta variante="aviso">
            Monte as provas antes de ver os gabaritos e exportar.{" "}
            <Link to="/sessoes/$sessaoId/provas" params={{ sessaoId }} className="underline">
              Ir para as provas
            </Link>
          </Alerta>
        ))}

      <div className="flex flex-wrap gap-4 font-grotesca text-detalhe">
        <Link to="/sessoes/$sessaoId/provas" params={{ sessaoId }} className="underline">
          Voltar às provas
        </Link>
        <Link to="/" className="underline">
          Voltar às sessões
        </Link>
      </div>
    </div>
  );
}

function ConteudoEntrega({ bancoId, sessaoId }: { bancoId: number; sessaoId: number }) {
  const provas = useProvasDoBanco(bancoId);

  if (provas.isError) return <Alerta variante="erro">{provas.error.message}</Alerta>;
  if (!provas.data) {
    return <p className="font-grotesca text-detalhe text-texto-suave">Carregando as provas…</p>;
  }
  return (
    <>
      <Gabaritos provas={provas.data} />
      <Exportacao bancoId={bancoId} sessaoId={sessaoId} />
    </>
  );
}
