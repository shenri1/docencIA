import { setupWorker } from "msw/browser";
import { criarHandlers } from "./backendFalso";

export const worker = setupWorker(...criarHandlers(import.meta.env.VITE_API_URL ?? "/api"));
