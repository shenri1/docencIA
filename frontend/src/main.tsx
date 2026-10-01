import "@fontsource-variable/hanken-grotesk";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";
import { QueryClient } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppRaiz } from "./app/AppRaiz";
import { criarApp } from "./app/criarApp";
import "./index.css";

// A API não tem prefixo de rota; em dev o proxy do Vite atende /api e o remove.
const BASE_DA_API = import.meta.env.VITE_API_URL ?? "/api";

async function iniciar() {
  // `bun run dev:mocks`: interface sem back-end, contra o back-end falso.
  if (import.meta.env.VITE_USE_MOCKS === "true") {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass" });
  }

  const app = criarApp({
    baseUrl: BASE_DA_API,
    queryClient: new QueryClient({
      defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
    }),
  });

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AppRaiz app={app} />
    </StrictMode>,
  );
}

void iniciar();
