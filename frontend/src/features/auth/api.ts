import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@tanstack/react-router";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import type { Docente } from "../../api/tipos";
import { guardarToken, limparToken } from "../../auth/token";

export const CHAVE_DOCENTE = ["docente"] as const;

interface Credenciais {
  credencial: string;
  senha: string;
}

export function useDocenteAtual() {
  const cliente = useApi();
  return useQuery<Docente>({
    queryKey: CHAVE_DOCENTE,
    queryFn: () => desembrulhar(cliente.GET("/auth/me")),
    staleTime: 5 * 60 * 1000,
  });
}

/** Sair é só esquecer o token: não há refresh nem rota de logout na API. */
export function useSair() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return () => {
    limparToken();
    queryClient.clear();
    void router.navigate({ to: "/login" });
  };
}

interface DadosCadastro {
  nome: string;
  credencial: string;
  senha: string;
}

export function useRegistrar() {
  const cliente = useApi();
  return useMutation<Docente, Error, DadosCadastro>({
    mutationFn: ({ nome, credencial, senha }) =>
      desembrulhar(
        cliente.POST("/auth/registrar", {
          body: { nome, credencial_institucional: credencial, senha },
        }),
      ),
  });
}

/** Login e leitura do docente: o token só fica guardado se `/auth/me` também der certo. */
export function useLogin() {
  const cliente = useApi();
  const queryClient = useQueryClient();

  return useMutation<Docente, Error, Credenciais>({
    mutationFn: async ({ credencial, senha }) => {
      const token = await desembrulhar(
        cliente.POST("/auth/login", {
          body: { username: credencial, password: senha, scope: "" },
          // OAuth2 password flow: formulário, não JSON.
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          bodySerializer: (corpo) =>
            new URLSearchParams(corpo as unknown as Record<string, string>),
        }),
      );
      guardarToken(token.access_token);
      try {
        const docente = await desembrulhar(cliente.GET("/auth/me"));
        queryClient.setQueryData(CHAVE_DOCENTE, docente);
        return docente;
      } catch (erro) {
        limparToken();
        throw erro;
      }
    },
  });
}
