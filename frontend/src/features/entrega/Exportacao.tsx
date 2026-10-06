import { useState } from "react";
import { ErroApi } from "../../api/erros";
import type { Exportacao as Registro } from "../../api/tipos";
import { useApi } from "../../app/api-context";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { baixarExportacao, useExportacoes, useExportar } from "./api";

const ROTULO_TIPO: Record<Registro["tipo"], { nome: string; descricao: string }> = {
  conteudo_puro: { nome: "Conteúdo puro", descricao: "a prova para aplicar" },
  metadados: { nome: "Metadados", descricao: "gabarito comentado, fontes e auditorias" },
};

const data = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

/** Revisões da mais recente para a mais antiga. */
function porRevisao(registros: Registro[]): [number, Registro[]][] {
  const grupos = new Map<number, Registro[]>();
  for (const registro of registros) {
    grupos.set(registro.revisao_banco, [...(grupos.get(registro.revisao_banco) ?? []), registro]);
  }
  return [...grupos.entries()].sort(([a], [b]) => b - a);
}

export function Exportacao({ bancoId, sessaoId }: { bancoId: number; sessaoId: number }) {
  const exportacoes = useExportacoes(bancoId);
  const exportar = useExportar(bancoId, sessaoId);

  return (
    <section aria-labelledby="titulo-exportacao" className="flex flex-col gap-4">
      <h2 id="titulo-exportacao" className="font-serifa text-subtitulo">
        Exportação DOCX
      </h2>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Gera dois arquivos da revisão atual do banco: o conteúdo puro, para aplicar, e os
        metadados, com gabarito comentado, fontes e auditorias. Exportar de novo a mesma
        revisão devolve os mesmos arquivos.
      </p>
      {exportar.error && <ErroExportacao erro={exportar.error} />}
      <div className="flex justify-end">
        <Botao disabled={exportar.isPending} onClick={() => exportar.mutate()}>
          {exportar.isPending ? "Exportando…" : "Exportar DOCX"}
        </Botao>
      </div>

      {exportacoes.isError && <Alerta variante="erro">{exportacoes.error.message}</Alerta>}
      {exportacoes.data && exportacoes.data.length === 0 && (
        <p className="font-grotesca text-detalhe text-texto-suave">
          Nenhum arquivo foi gerado ainda.
        </p>
      )}
      {porRevisao(exportacoes.data ?? []).map(([revisao, registros]) => (
        <div key={revisao} className="flex flex-col gap-2">
          <h3 className="tabular font-grotesca text-detalhe font-semibold">Revisão r{revisao}</h3>
          <ul className="flex flex-col gap-3">
            {registros.map((registro) => (
              <ArquivoExportado key={registro.id} registro={registro} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

/** 409 da checagem pré-DOCX é orientação, com cada problema listado. */
function ErroExportacao({ erro }: { erro: Error }) {
  const api = erro instanceof ErroApi ? erro : null;
  const bruto = api?.extras.problemas;
  const problemas = Array.isArray(bruto)
    ? bruto.filter((p): p is string => typeof p === "string")
    : [];
  return (
    <Alerta variante={api?.status === 409 ? "aviso" : "erro"}>
      <p>{erro.message}</p>
      {problemas.length > 0 && (
        <ul className="mt-1 list-disc pl-5">
          {problemas.map((problema) => (
            <li key={problema}>{problema}</li>
          ))}
        </ul>
      )}
    </Alerta>
  );
}

function ArquivoExportado({ registro }: { registro: Registro }) {
  const cliente = useApi();
  const [erro, setErro] = useState<string | null>(null);
  const [baixando, setBaixando] = useState(false);
  const tipo = ROTULO_TIPO[registro.tipo];

  async function baixar() {
    setErro(null);
    setBaixando(true);
    try {
      await baixarExportacao(cliente, registro.id);
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e));
    } finally {
      setBaixando(false);
    }
  }

  return (
    <li>
      <article
        aria-label={`${tipo.nome}, revisão r${registro.revisao_banco}`}
        className="cartao flex flex-col gap-2 p-4 font-grotesca text-detalhe"
      >
        <p>
          <span className="font-semibold">{tipo.nome}</span> — {tipo.descricao}
        </p>
        <p className="tabular text-texto-suave">{data.format(new Date(registro.criado_em))}</p>
        <p className="tabular break-all">{`sha256: ${registro.hash_conteudo}`}</p>
        <p className="text-texto-suave">
          Confira com <code>sha256sum</code> no arquivo baixado.
        </p>
        {erro && <Alerta variante="erro">{erro}</Alerta>}
        <div className="flex justify-end">
          <Botao variante="fantasma" disabled={baixando} onClick={() => void baixar()}>
            {baixando ? "Baixando…" : "Baixar"}
          </Botao>
        </div>
      </article>
    </li>
  );
}
