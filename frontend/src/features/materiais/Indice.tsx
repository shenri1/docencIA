import { Link, useNavigate } from "@tanstack/react-router";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { PASSOS_NOVA_SESSAO, Passos } from "../../components/Passos";
import { formatarTamanho, rotuloDePaginas } from "../../lib/formatar";
import {
  useConfirmarIndice,
  useIndice,
  useRemoverMaterial,
  useSairDoM1SeJaConfirmado,
} from "./api";
import { ROTULO_FORMATO, ROTULO_ORIGEM, ROTULO_TIPO } from "./rotulos";

export function Indice({ sessaoId }: { sessaoId: string }) {
  const id = Number(sessaoId);
  const navigate = useNavigate();
  useSairDoM1SeJaConfirmado(id);
  const indice = useIndice(id);
  const remover = useRemoverMaterial(id);
  const confirmar = useConfirmarIndice(id);

  const materiais = indice.data?.materiais ?? [];
  const vazio = indice.data !== undefined && materiais.length === 0;

  function aoConfirmar() {
    confirmar.mutate(undefined, {
      onSuccess: () =>
        void navigate({
          to: "/sessoes/$sessaoId",
          params: { sessaoId },
        }),
    });
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="font-serifa text-titulo">Índice de materiais</h1>
        <Passos passos={PASSOS_NOVA_SESSAO} atual={3} />
        <p className="font-grotesca text-detalhe text-texto-suave">
          Confira o que foi enviado. Os identificadores (S1, P1…) são os que
          aparecem nas fontes de cada questão.
        </p>
      </div>

      {indice.isError && <Alerta variante="erro">{indice.error.message}</Alerta>}
      {remover.error && <Alerta variante="erro">{remover.error.message}</Alerta>}
      {confirmar.error && (
        <Alerta variante="erro">{confirmar.error.message}</Alerta>
      )}

      {vazio && (
        <div className="cartao flex flex-col items-start gap-3 p-6">
          <p className="font-serifa text-corpo-lg">Nenhum material enviado.</p>
          <p className="font-grotesca text-detalhe text-texto-suave">
            Envie ao menos um material antes de confirmar o índice.
          </p>
        </div>
      )}

      {materiais.length > 0 && (
        <div className="cartao overflow-x-auto">
          <table className="w-full text-left font-grotesca text-detalhe">
            <caption className="sr-only">Materiais da sessão</caption>
            <thead>
              <tr className="border-b border-borda text-rotulo text-texto-suave">
                <th scope="col" className="px-4 py-3">Id</th>
                <th scope="col" className="px-4 py-3">Arquivo</th>
                <th scope="col" className="px-4 py-3">Tipo</th>
                <th scope="col" className="px-4 py-3">Formato</th>
                <th scope="col" className="px-4 py-3 text-right">Páginas</th>
                <th scope="col" className="px-4 py-3">Origem do texto</th>
                <th scope="col" className="px-4 py-3 text-right">Tamanho</th>
                <th scope="col" className="px-4 py-3">
                  <span className="sr-only">Ações</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {materiais.map((m) => (
                <tr key={m.id} className="border-b border-borda last:border-b-0">
                  <td className="px-4 py-3 font-semibold">{m.identificador_curto}</td>
                  <td className="break-words px-4 py-3 font-serifa text-corpo">
                    {m.nome_arquivo}
                  </td>
                  <td className="px-4 py-3">{ROTULO_TIPO[m.tipo]}</td>
                  <td className="px-4 py-3">{ROTULO_FORMATO[m.formato]}</td>
                  <td className="tabular px-4 py-3 text-right">
                    {rotuloDePaginas(m.contagem_paginas_logicas, m.formato) ?? "—"}
                  </td>
                  <td className="px-4 py-3">{ROTULO_ORIGEM[m.origem_texto]}</td>
                  <td className="tabular px-4 py-3 text-right">
                    {formatarTamanho(m.tamanho_bytes)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Botao
                      variante="descartar"
                      aria-label={`Remover ${m.nome_arquivo}`}
                      disabled={remover.isPending || confirmar.isPending}
                      onClick={() => remover.mutate(m.id)}
                    >
                      Remover
                    </Botao>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmar.isPending && (
        <p role="status" className="font-grotesca text-detalhe">
          Indexando os materiais… isso pode levar alguns minutos. Não feche esta
          página.
        </p>
      )}

      <div className="flex flex-col gap-3 border-t border-borda pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-1">
          <Link
            to="/sessoes/$sessaoId/materiais"
            params={{ sessaoId }}
            className="font-grotesca text-detalhe underline"
          >
            Voltar aos materiais
          </Link>
          <p className="font-grotesca text-detalhe text-texto-suave">
            Depois de confirmar, não será mais possível enviar ou remover
            materiais desta sessão.
          </p>
        </div>
        <Botao
          disabled={materiais.length === 0 || confirmar.isPending || indice.isPending}
          onClick={aoConfirmar}
        >
          Confirmar índice
        </Botao>
      </div>
    </div>
  );
}
