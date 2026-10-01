import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import type { App } from "./criarApp";
import { ApiProvider } from "./api-context";

export function AppRaiz({ app }: { app: App }) {
  return (
    <QueryClientProvider client={app.queryClient}>
      <ApiProvider value={app.cliente}>
        <RouterProvider router={app.router} />
      </ApiProvider>
    </QueryClientProvider>
  );
}
