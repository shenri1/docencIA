import { Link, useRouter, useSearch } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { Marca } from "../../components/Marca";
import { destinoSeguro } from "./destinoSeguro";
import { useLogin } from "./api";

export function Login() {
  const router = useRouter();
  const { redirect, criada } = useSearch({ from: "/login" });
  const login = useLogin();
  const [credencial, setCredencial] = useState("");
  const [senha, setSenha] = useState("");
  const [tentou, setTentou] = useState(false);

  const erroCredencial = credencial.trim()
    ? null
    : "Informe sua credencial institucional.";
  const erroSenha = senha ? null : "Informe sua senha.";

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    setTentou(true);
    if (erroCredencial || erroSenha) return;
    login.mutate(
      { credencial: credencial.trim(), senha },
      { onSuccess: () => router.history.push(destinoSeguro(redirect)) },
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-5 py-10">
      <Marca />
      <div className="folha flex flex-col gap-5 p-6">
        <h1 className="font-serifa text-subtitulo">Entrar</h1>
        {criada && (
          <Alerta variante="sucesso">
            Conta criada. Entre com sua credencial institucional e sua senha.
          </Alerta>
        )}
        {login.error && <Alerta variante="erro">{login.error.message}</Alerta>}
        <form noValidate onSubmit={enviar} className="flex flex-col gap-4">
          <Campo
            rotulo="Credencial institucional"
            autoComplete="username"
            value={credencial}
            onChange={(e) => setCredencial(e.target.value)}
            erro={tentou ? erroCredencial : null}
          />
          <Campo
            rotulo="Senha"
            type="password"
            autoComplete="current-password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            erro={tentou ? erroSenha : null}
          />
          <Botao type="submit" disabled={login.isPending}>
            {login.isPending ? "Entrando…" : "Entrar"}
          </Botao>
        </form>
        <p className="font-grotesca text-detalhe text-texto-suave">
          Esqueceu a senha? Não há recuperação por e-mail: procure o
          administrador do sistema da sua instituição.
        </p>
      </div>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Ainda não tem conta?{" "}
        <Link to="/cadastro" className="underline">
          Criar conta
        </Link>
      </p>
    </main>
  );
}
