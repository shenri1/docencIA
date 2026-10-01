import { Link } from "@tanstack/react-router";
import { useState, type ChangeEvent, type DragEvent } from "react";
import type { Material, TipoMaterial } from "../../api/tipos";
import { ErroApi } from "../../api/erros";
import { Botao } from "../../components/Botao";
import { CampoSelecao } from "../../components/Campo";
import { IconeErro, IconeOk } from "../../components/Icones";
import { PASSOS_NOVA_SESSAO, Passos } from "../../components/Passos";
import { formatarTamanho, rotuloDePaginas } from "../../lib/formatar";
import {
  useEnviarMaterial,
  useIndice,
  useSairDoM1SeJaConfirmado,
} from "./api";
import { ROTULO_ORIGEM, ROTULO_TIPO } from "./rotulos";

type EstadoItem = "aguardando" | "enviando" | "enviado" | "recusado";

interface ItemFila {
  id: number;
  arquivo: File;
  tipo: TipoMaterial | "";
  estado: EstadoItem;
  material?: Material;
  erro?: ErroApi;
}

// Recusas que dizem respeito ao arquivo, não ao sistema ou ao estado da sessão.
const STATUS_DE_ARQUIVO = [413, 415, 422];
const FORMATOS_ACEITOS = "PDF, PPTX, DOCX e TXT";

function DetalheDoEnvio({ item }: { item: ItemFila }) {
  if (item.estado === "aguardando") {
    return <span className="text-texto-suave">Aguardando envio</span>;
  }
  if (item.estado === "enviando") {
    return <span role="status">Processando…</span>;
  }
  if (item.estado === "enviado" && item.material) {
    const m = item.material;
    const partes = [
      m.identificador_curto,
      rotuloDePaginas(m.contagem_paginas_logicas, m.formato),
      ROTULO_ORIGEM[m.origem_texto],
    ].filter(Boolean);
    return (
      <span className="flex items-center gap-1.5 text-manter">
        <IconeOk />
        <span>{partes.join(" · ")}</span>
      </span>
    );
  }
  const erro = item.erro;
  if (!erro) return null;
  const paginas = erro.extras.paginas_afetadas;
  const motivo = erro.extras.motivo;
  return (
    <div role="alert" className="flex flex-col gap-1 text-descartar">
      <span className="flex items-start gap-1.5">
        <span className="mt-0.5 shrink-0">
          <IconeErro />
        </span>
        <span>{erro.message}</span>
      </span>
      {typeof motivo === "string" && <span>Causa: {motivo}</span>}
      {Array.isArray(paginas) && paginas.length > 0 && (
        <span>Páginas afetadas: {paginas.join(", ")}</span>
      )}
      {STATUS_DE_ARQUIVO.includes(erro.status) && (
        <span className="text-texto-suave">Formatos aceitos: {FORMATOS_ACEITOS}.</span>
      )}
    </div>
  );
}

export function Materiais({ sessaoId }: { sessaoId: string }) {
  const id = Number(sessaoId);
  useSairDoM1SeJaConfirmado(id);
  const indice = useIndice(id);
  const enviar = useEnviarMaterial(id);
  const [itens, setItens] = useState<ItemFila[]>([]);
  const [proximoId, setProximoId] = useState(1);
  const [enviando, setEnviando] = useState(false);

  const jaEnviados = indice.data?.materiais.length ?? 0;
  const pendentes = itens.filter(
    (i) => i.estado === "aguardando" || i.estado === "recusado",
  );
  const podeEnviar =
    !enviando && pendentes.length > 0 && pendentes.every((i) => i.tipo !== "");

  function adicionar(arquivos: File[]) {
    if (arquivos.length === 0) return;
    setItens((atuais) => [
      ...atuais,
      ...arquivos.map((arquivo, i) => ({
        id: proximoId + i,
        arquivo,
        tipo: "" as const,
        estado: "aguardando" as const,
      })),
    ]);
    setProximoId((n) => n + arquivos.length);
  }

  function aoEscolher(evento: ChangeEvent<HTMLInputElement>) {
    adicionar(Array.from(evento.target.files ?? []));
    evento.target.value = "";
  }

  function aoSoltar(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault();
    adicionar(Array.from(evento.dataTransfer.files));
  }

  function atualizar(itemId: number, mudanca: Partial<ItemFila>) {
    setItens((atuais) =>
      atuais.map((i) => (i.id === itemId ? { ...i, ...mudanca } : i)),
    );
  }

  // Um arquivo por vez: a extração (OCR incluído) é pesada no servidor, e a
  // ordem de envio define os identificadores curtos (S1, P1...).
  async function enviarTodos() {
    setEnviando(true);
    for (const item of pendentes) {
      atualizar(item.id, { estado: "enviando", erro: undefined });
      try {
        const material = await enviar.mutateAsync({
          tipo: item.tipo as TipoMaterial,
          arquivo: item.arquivo,
        });
        atualizar(item.id, { estado: "enviado", material });
      } catch (erro) {
        atualizar(item.id, {
          estado: "recusado",
          erro:
            erro instanceof ErroApi ? erro : new ErroApi(0, "Falha ao enviar o arquivo."),
        });
      }
    }
    setEnviando(false);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="font-serifa text-titulo">Materiais da sessão</h1>
        <Passos passos={PASSOS_NOVA_SESSAO} atual={2} />
        <p className="font-grotesca text-detalhe text-texto-suave">
          O sistema só usa como fonte o que você enviar aqui. Formatos aceitos:{" "}
          {FORMATOS_ACEITOS}.
        </p>
      </div>

      <div
        data-testid="zona-de-arquivos"
        onDragOver={(e) => e.preventDefault()}
        onDrop={aoSoltar}
        className="cartao flex flex-col items-center gap-3 border-dashed p-8 text-center"
      >
        <p className="font-serifa text-corpo-lg">Arraste os arquivos para cá</p>
        <input
          id="selecionar-arquivos"
          type="file"
          multiple
          accept=".pdf,.pptx,.docx,.txt"
          onChange={aoEscolher}
          className="peer sr-only"
        />
        <label
          htmlFor="selecionar-arquivos"
          className="botao botao-primario peer-focus-visible:outline peer-focus-visible:outline-1 peer-focus-visible:outline-offset-2"
        >
          Selecionar arquivos
        </label>
      </div>

      {itens.length > 0 && (
        <section aria-label="Fila de envio" className="flex flex-col gap-3">
          <ul className="flex flex-col gap-3">
            {itens.map((item) => {
              const editavel = item.estado === "aguardando" || item.estado === "recusado";
              return (
                <li
                  key={item.id}
                  className="cartao grid gap-3 p-4 sm:grid-cols-[1fr_12rem] sm:items-start"
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="break-words font-serifa text-corpo-lg">
                      {item.arquivo.name}
                    </span>
                    <span className="tabular font-grotesca text-detalhe text-texto-suave">
                      {formatarTamanho(item.arquivo.size)}
                    </span>
                    <div className="font-grotesca text-detalhe">
                      <DetalheDoEnvio item={item} />
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <CampoSelecao
                      rotulo="Tipo didático"
                      value={item.tipo}
                      disabled={!editavel}
                      onChange={(e) =>
                        atualizar(item.id, { tipo: e.target.value as TipoMaterial })
                      }
                    >
                      <option value="" disabled>
                        Escolha o tipo
                      </option>
                      {(Object.keys(ROTULO_TIPO) as TipoMaterial[]).map((tipo) => (
                        <option key={tipo} value={tipo}>
                          {ROTULO_TIPO[tipo]}
                        </option>
                      ))}
                    </CampoSelecao>
                    {editavel && (
                      <Botao
                        variante="fantasma"
                        aria-label={`Tirar ${item.arquivo.name} da fila`}
                        disabled={enviando}
                        onClick={() =>
                          setItens((atuais) => atuais.filter((i) => i.id !== item.id))
                        }
                      >
                        Tirar da fila
                      </Botao>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="flex justify-end">
            <Botao disabled={!podeEnviar} onClick={() => void enviarTodos()}>
              {enviando ? "Enviando…" : "Enviar arquivos"}
            </Botao>
          </div>
        </section>
      )}

      {jaEnviados > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-borda pt-4">
          <p className="font-grotesca text-detalhe">
            {jaEnviados} {jaEnviados === 1 ? "material já enviado" : "materiais já enviados"}
          </p>
          <Link
            to="/sessoes/$sessaoId/indice"
            params={{ sessaoId }}
            className="botao botao-primario"
          >
            Continuar para o índice
          </Link>
        </div>
      )}
    </div>
  );
}
