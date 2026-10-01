import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// A API não tem prefixo de rota (/sessoes, /auth...), e a SPA também usa
// /sessoes/:id. Por isso o navegador chama a API sob /api e o proxy tira o
// prefixo. Em produção o servidor web precisa fazer a mesma reescrita.
const API_ALVO = process.env.API_ALVO ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": {
        target: API_ALVO,
        changeOrigin: true,
        rewrite: (caminho) => caminho.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    env: { VITE_API_URL: "http://api.test" },
  },
});
