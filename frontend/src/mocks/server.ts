import { setupServer } from "msw/node";

// Sem handlers por padrão: cada teste declara os que usa com server.use(...),
// e onUnhandledRequest:"error" faz chamada não prevista falhar em vez de passar.
export const server = setupServer();
