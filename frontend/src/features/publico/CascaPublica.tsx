import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Marca } from "../../components/Marca";

/** Cabeçalho e rodapé das páginas públicas: landing e política de privacidade. */
export function CascaPublica({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-borda bg-cartao">
        <div className="mx-auto flex max-w-leitura items-center justify-between gap-4 px-5 py-3 md:px-12">
          <Link to="/" aria-label="docencIA — início">
            <Marca />
          </Link>
          <nav aria-label="Acesso" className="flex items-center gap-3 font-grotesca text-detalhe">
            <Link to="/login" className="underline">
              Entrar
            </Link>
            <Link to="/cadastro" className="botao botao-primario">
              Criar conta
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-leitura flex-1 px-5 py-10 md:px-12">{children}</main>
      <footer className="border-t border-borda">
        <div className="mx-auto flex max-w-leitura flex-wrap items-center justify-between gap-3 px-5 py-6 font-grotesca text-detalhe text-texto-suave md:px-12">
          <span>TCC de Engenharia da Computação — UEMA</span>
          <Link to="/privacidade" className="underline">
            Política de privacidade
          </Link>
        </div>
      </footer>
    </div>
  );
}
