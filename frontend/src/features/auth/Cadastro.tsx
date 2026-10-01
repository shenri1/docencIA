import { Link, useRouter } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { ErroApi } from "../../api/erros";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Caixa } from "../../components/Caixa";
import { Campo } from "../../components/Campo";
import { Marca } from "../../components/Marca";
import { mensagemDeSenha } from "../../lib/validacao";
import { useRegistrar } from "./api";

// Nomes dos campos como a API os devolve no 422.
const CAMPO_DA_API = {
  nome: "nome",
  credencial_institucional: "credencial",
  senha: "senha",
} as const;

export function Cadastro() {
  const router = useRouter();
  const registrar = useRegistrar();
  const [nome, setNome] = useState("");
  const [credencial, setCredencial] = useState("");
  const [senha, setSenha] = useState("");
  const [lgpd, setLgpd] = useState(false);
  const [tentou, setTentou] = useState(false);

  const erros = {
    nome: nome.trim() ? null : "Informe seu nome completo.",
    credencial: credencial.trim()
      ? null
      : "Informe sua credencial institucional.",
    senha: mensagemDeSenha(senha),
    lgpd: lgpd ? null : "Aceite o tratamento de dados para criar a conta.",
  };

  const erroApi = registrar.error instanceof ErroApi ? registrar.error : null;
  const doServidor = (campoApi: keyof typeof CAMPO_DA_API) =>
    erroApi?.campos?.find((c) => c.campo === campoApi)?.mensagem ?? null;

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    setTentou(true);
    if (Object.values(erros).some(Boolean)) return;
    registrar.mutate(
      { nome: nome.trim(), credencial: credencial.trim(), senha },
      {
        onSuccess: () =>
          void router.navigate({ to: "/login", search: { criada: true } }),
      },
    );
  }

  const campoDoErro = (campo: keyof typeof erros, campoApi: keyof typeof CAMPO_DA_API) =>
    (tentou ? erros[campo] : null) ?? doServidor(campoApi);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 px-5 py-10">
      <Marca />
      <div className="folha flex flex-col gap-5 p-6">
        <h1 className="font-serifa text-subtitulo">Criar conta</h1>
        {erroApi && !erroApi.campos && (
          <Alerta variante="erro">{erroApi.message}</Alerta>
        )}
        <form noValidate onSubmit={enviar} className="flex flex-col gap-4">
          <Campo
            rotulo="Nome completo"
            autoComplete="name"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            erro={campoDoErro("nome", "nome")}
          />
          <Campo
            rotulo="Credencial institucional"
            autoComplete="username"
            ajuda="Seu identificador de login, por exemplo a matrícula."
            value={credencial}
            onChange={(e) => setCredencial(e.target.value)}
            erro={campoDoErro("credencial", "credencial_institucional")}
          />
          <Campo
            rotulo="Senha"
            type="password"
            autoComplete="new-password"
            ajuda="De 8 a 72 bytes; letras acentuadas contam como 2."
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            erro={campoDoErro("senha", "senha")}
          />
          <Caixa
            rotulo="Concordo com o tratamento dos meus dados pessoais, conforme a LGPD."
            checked={lgpd}
            onChange={(e) => setLgpd(e.target.checked)}
            erro={tentou ? erros.lgpd : null}
          />
          <Botao type="submit" disabled={registrar.isPending}>
            {registrar.isPending ? "Criando conta…" : "Criar conta"}
          </Botao>
        </form>
      </div>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Já tem conta?{" "}
        <Link to="/login" className="underline">
          Entrar
        </Link>
      </p>
    </main>
  );
}
