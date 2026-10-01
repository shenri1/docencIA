/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base da API. Padrão: /api (proxy do Vite em dev). */
  readonly VITE_API_URL?: string;
  /** "true" liga o back-end falso (MSW no navegador). */
  readonly VITE_USE_MOCKS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
