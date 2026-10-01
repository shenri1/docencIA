import { createContext, useContext } from "react";
import type { ClienteApi } from "../api/cliente";

const ApiContext = createContext<ClienteApi | null>(null);

export const ApiProvider = ApiContext.Provider;

export function useApi(): ClienteApi {
  const cliente = useContext(ApiContext);
  if (cliente === null) throw new Error("useApi fora do ApiProvider");
  return cliente;
}
