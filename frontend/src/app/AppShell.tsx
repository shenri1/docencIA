import { Link, Outlet } from "@tanstack/react-router";
import { useDocenteAtual, useSair } from "../features/auth/api";
import { Botao } from "../components/Botao";
import { Marca } from "../components/Marca";

export function AppShell() {
  const docente = useDocenteAtual();
  const sair = useSair();

  return (
    <div className="min-h-screen">
      <header className="border-b border-borda bg-cartao">
        <div className="mx-auto flex max-w-leitura items-center justify-between gap-4 px-5 py-3 md:px-12">
          <Link to="/" aria-label="docencIA — início">
            <Marca />
          </Link>
          <div className="flex items-center gap-3 font-grotesca text-detalhe">
            {docente.data?.perfil === "administrador" && (
              <Link to="/admin/prompts" className="underline">
                Administração
              </Link>
            )}
            {docente.data && <span>{docente.data.nome}</span>}
            <Botao variante="fantasma" onClick={sair}>
              Sair
            </Botao>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-leitura px-5 py-8 md:px-12">
        <Outlet />
      </main>
    </div>
  );
}
