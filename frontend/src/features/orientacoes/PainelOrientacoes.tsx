import { useState, type FormEvent, type ReactNode } from "react";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { mensagemDeErro } from "../banco/curadoria";
import {
  contar,
  TETO_ATIVAS,
  TETO_CRUZAMENTOS,
  useCriarOrientacao,
  useDesativarOrientacao,
  useOrientacoes,
} from "./api";
import { textoOrientacao } from "./texto";

interface Props {
  sessaoId: number;
  /** Na mesa o painel fica recolhido: a curadoria é o foco da tela. */
  recolhido?: boolean;
}

export function PainelOrientacoes({ sessaoId, recolhido = false }: Props) {
  const lista = useOrientacoes(sessaoId);
  const criar = useCriarOrientacao(sessaoId);
  const desativar = useDesativarOrientacao(sessaoId);
  const [texto, setTexto] = useState("");

  const orientacoes = lista.data ?? [];
  const ativas = orientacoes.filter((o) => o.estado === "ativa");
  const { ativas: n, comCruzamento } = contar(orientacoes);
  const cheio = n >= TETO_ATIVAS;
  const erro = criar.error ?? desativar.error;

  function acrescentar(evento: FormEvent) {
    evento.preventDefault();
    const limpo = texto.trim();
    if (!limpo || cheio) return;
    criar.mutate(limpo, { onSuccess: () => setTexto("") });
  }

  const contador = (
    <p className="tabular font-grotesca text-detalhe text-texto-suave">
      {n}/{TETO_ATIVAS} · {comCruzamento}/{TETO_CRUZAMENTOS} com articulação
    </p>
  );
  const conteudo: ReactNode = (
    <>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Valem para as próximas questões geradas nesta sessão. Nunca ampliam a fonte além do
        seu material.
      </p>
      {lista.isError && <Alerta variante="erro">{lista.error.message}</Alerta>}
      {erro && <Alerta variante="erro">{mensagemDeErro(erro)}</Alerta>}
      {ativas.length === 0 ? (
        <p className="font-grotesca text-detalhe text-texto-suave">Nenhuma orientação ativa.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {ativas.map((o) => (
            <li
              key={o.id}
              className="flex flex-wrap items-center justify-between gap-2 font-grotesca text-detalhe"
            >
              <span>{textoOrientacao(o)}</span>
              <Botao
                variante="fantasma"
                disabled={desativar.isPending}
                onClick={() => desativar.mutate(o.id)}
              >
                Desativar
              </Botao>
            </li>
          ))}
        </ul>
      )}
      <form noValidate onSubmit={acrescentar} className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <Campo
            rotulo="Nova orientação"
            value={texto}
            maxLength={500}
            onChange={(e) => setTexto(e.target.value)}
            ajuda={cheio ? "Desative uma orientação para acrescentar outra." : undefined}
          />
        </div>
        <Botao type="submit" disabled={cheio || !texto.trim() || criar.isPending}>
          Acrescentar
        </Botao>
      </form>
    </>
  );

  if (recolhido) {
    return (
      <details className="cartao p-5">
        <summary className="cursor-pointer font-grotesca text-detalhe">
          Orientações da sessão ({n} {n === 1 ? "ativa" : "ativas"})
        </summary>
        <section aria-label="Orientações da sessão" className="mt-3 flex flex-col gap-3">
          {contador}
          {conteudo}
        </section>
      </details>
    );
  }
  return (
    <section aria-label="Orientações da sessão" className="cartao flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-grotesca text-rotulo-lg">Orientações da sessão</h2>
        {contador}
      </div>
      {conteudo}
    </section>
  );
}
