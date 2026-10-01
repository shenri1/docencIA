import type { QueryClient } from "@tanstack/react-query";
import {
  type RouterHistory,
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";
import type { ClienteApi } from "./api/cliente";
import { AppShell } from "./app/AppShell";
import { lerToken } from "./auth/token";
import { AreaAdmin } from "./features/admin/AreaAdmin";
import { Logs } from "./features/admin/Logs";
import { Prompts } from "./features/admin/Prompts";
import { Geracao } from "./features/banco/Geracao";
import { BancoProvisorio } from "./features/banco/BancoProvisorio";
import { Cadastro } from "./features/auth/Cadastro";
import { Login } from "./features/auth/Login";
import { NovaSessao } from "./features/sessoes/NovaSessao";
import { Indice } from "./features/materiais/Indice";
import { Materiais } from "./features/materiais/Materiais";
import { Painel } from "./features/sessoes/Painel";
import { SessaoPorMarco } from "./features/sessoes/SessaoPorMarco";

export interface ContextoRota {
  queryClient: QueryClient;
  cliente: ClienteApi;
}

const raiz = createRootRouteWithContext<ContextoRota>()({ component: Outlet });

const login = createRoute({
  getParentRoute: () => raiz,
  path: "/login",
  // Parâmetros opcionais no tipo de retorno: quem navega para /login não é
  // obrigado a informá-los.
  validateSearch: (
    busca: Record<string, unknown>,
  ): { redirect?: string; criada?: true } => ({
    redirect: typeof busca.redirect === "string" ? busca.redirect : undefined,
    // Vem do cadastro; a URL a entrega como número, texto ou booleano.
    criada:
      busca.criada === true || busca.criada === 1 || busca.criada === "1"
        ? true
        : undefined,
  }),
  beforeLoad: () => {
    if (lerToken()) throw redirect({ to: "/" });
  },
  component: Login,
});

const cadastro = createRoute({
  getParentRoute: () => raiz,
  path: "/cadastro",
  beforeLoad: () => {
    if (lerToken()) throw redirect({ to: "/" });
  },
  component: Cadastro,
});

// Layout sem caminho: tudo que mora aqui exige token. Sem ele, o login recebe a
// rota de destino para devolver o docente a ela depois.
const autenticado = createRoute({
  getParentRoute: () => raiz,
  id: "autenticado",
  beforeLoad: ({ location }) => {
    if (!lerToken()) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
  },
  component: AppShell,
});

const painel = createRoute({
  getParentRoute: () => autenticado,
  path: "/",
  validateSearch: (busca: Record<string, unknown>): { pagina?: number } => {
    const pagina = Number(busca.pagina);
    return { pagina: Number.isInteger(pagina) && pagina > 1 ? pagina : undefined };
  },
  component: function RotaPainel() {
    const { pagina } = painel.useSearch();
    return <Painel pagina={pagina ?? 1} />;
  },
});

const sessao = createRoute({
  getParentRoute: () => autenticado,
  path: "/sessoes/$sessaoId",
  component: function RotaSessao() {
    const { sessaoId } = sessao.useParams();
    return <SessaoPorMarco sessaoId={sessaoId} />;
  },
});

const banco = createRoute({
  getParentRoute: () => autenticado,
  path: "/sessoes/$sessaoId/banco",
  component: function RotaBanco() {
    const { sessaoId } = banco.useParams();
    return <BancoProvisorio sessaoId={sessaoId} />;
  },
});

const geracao = createRoute({
  getParentRoute: () => autenticado,
  path: "/sessoes/$sessaoId/geracao",
  component: function RotaGeracao() {
    const { sessaoId } = geracao.useParams();
    return <Geracao sessaoId={sessaoId} />;
  },
});

const novaSessao = createRoute({
  getParentRoute: () => autenticado,
  path: "/sessoes/nova",
  component: NovaSessao,
});

const materiais = createRoute({
  getParentRoute: () => autenticado,
  path: "/sessoes/$sessaoId/materiais",
  component: function RotaMateriais() {
    const { sessaoId } = materiais.useParams();
    return <Materiais sessaoId={sessaoId} />;
  },
});

const indice = createRoute({
  getParentRoute: () => autenticado,
  path: "/sessoes/$sessaoId/indice",
  component: function RotaIndice() {
    const { sessaoId } = indice.useParams();
    return <Indice sessaoId={sessaoId} />;
  },
});

// A casca esconde a área de quem não é administrador; quem decide é a API (403).
const admin = createRoute({
  getParentRoute: () => autenticado,
  path: "/admin",
  component: AreaAdmin,
});

const adminInicio = createRoute({
  getParentRoute: () => admin,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/admin/prompts", replace: true });
  },
});

const adminPrompts = createRoute({
  getParentRoute: () => admin,
  path: "prompts",
  component: Prompts,
});

const adminLogs = createRoute({
  getParentRoute: () => admin,
  path: "logs",
  component: Logs,
});

const arvore = raiz.addChildren([
  login,
  cadastro,
  autenticado.addChildren([
    painel,
    novaSessao,
    sessao,
    materiais,
    indice,
    banco,
    geracao,
    admin.addChildren([adminInicio, adminPrompts, adminLogs]),
  ]),
]);

export function criarRouter(contexto: ContextoRota, history?: RouterHistory) {
  return createRouter({ routeTree: arvore, context: contexto, history });
}

export type AppRouter = ReturnType<typeof criarRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
