import { Link, Outlet } from "@tanstack/react-router";
import { Alerta } from "../../components/Alerta";
import { useDocenteAtual } from "../auth/api";

/**
 * Casca da administração. Esconder a tela de quem não é administrador é só
 * conveniência: quem decide é a API, que responde 403.
 */
export function AreaAdmin() {
  const docente = useDocenteAtual();

  if (docente.isPending) {
    return <p className="font-grotesca text-detalhe text-texto-suave">Carregando…</p>;
  }
  if (docente.isError) {
    return <Alerta variante="erro">{docente.error.message}</Alerta>;
  }
  if (docente.data.perfil !== "administrador") {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <Alerta variante="info">Esta área é só para administradores.</Alerta>
        <Link to="/" className="font-grotesca text-detalhe underline">
          Voltar às sessões
        </Link>
      </div>
    );
  }

  const aba = "font-grotesca text-detalhe underline-offset-4 hover:underline";
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="font-serifa text-titulo">Administração</h1>
        <nav aria-label="Administração" className="flex gap-5 border-b border-borda pb-2">
          <Link
            to="/admin/prompts"
            className={aba}
            activeProps={{ className: "font-semibold underline" }}
          >
            Prompt mestre
          </Link>
          <Link
            to="/admin/logs"
            className={aba}
            activeProps={{ className: "font-semibold underline" }}
          >
            Log de auditoria
          </Link>
        </nav>
      </div>
      <Outlet />
    </div>
  );
}
