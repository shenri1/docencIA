import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import type { MarcoBanco } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { inteiroEntre } from "../../lib/validacao";
import { useMarcoSessao } from "../sessoes/api";
import { bancoMaisRecente } from "../sessoes/marco";
import { type Acumulado, type ParametrosGeracao, useGeracaoEmLotes } from "./api";

// Espelha N_MAXIMO_BANCO de backend/app/schemas/banco.py. Conveniência: a API
// continua sendo a autoridade (P10).
const N_MAXIMO_BANCO = 25;

const questoes = (n: number) => (n === 1 ? "questão" : "questões");

export function Geracao({ sessaoId }: { sessaoId: string }) {
  const id = Number(sessaoId);
  const marco = useMarcoSessao(id);
  const geracao = useGeracaoEmLotes(id);
  const banco = marco.data ? bancoMaisRecente(marco.data) : null;
  const rodando = geracao.estado !== "parado";

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <h1 className="font-serifa text-titulo">Geração do banco</h1>

      {marco.isError && <Alerta variante="erro">{marco.error.message}</Alerta>}
      {geracao.erro && <Alerta variante="erro">{geracao.erro.message}</Alerta>}

      {rodando && geracao.acumulado && (
        <Progresso
          acumulado={geracao.acumulado}
          pausando={geracao.estado === "pausando"}
          aoPausar={geracao.pausar}
        />
      )}

      {!rodando && marco.data && banco === null && (
        <Formulario aoGerar={(p) => void geracao.iniciar(p)} />
      )}

      {!rodando && banco !== null && (
        <SituacaoDoBanco
          banco={banco}
          sessaoId={sessaoId}
          aoContinuar={() => void geracao.continuar(banco.banco_id)}
        />
      )}

      {!rodando && geracao.acumulado && <Resumo acumulado={geracao.acumulado} />}

      <Link to="/sessoes" className="font-grotesca text-detalhe underline">
        Voltar às sessões
      </Link>
    </div>
  );
}

function Formulario({ aoGerar }: { aoGerar: (p: ParametrosGeracao) => void }) {
  const [versao, setVersao] = useState("v1");
  const [objetivas, setObjetivas] = useState("10");
  const [discursivas, setDiscursivas] = useState("0");

  const o = inteiroEntre(objetivas, 0, N_MAXIMO_BANCO);
  const d = inteiroEntre(discursivas, 0, N_MAXIMO_BANCO);
  const total = o !== null && d !== null ? o + d : null;
  const totalValido = total !== null && total >= 1 && total <= N_MAXIMO_BANCO;
  const valido = versao.trim() !== "" && totalValido;

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (valido) aoGerar({ versao: versao.trim(), n_objetivas: o!, n_discursivas: d! });
  }

  return (
    <form noValidate onSubmit={enviar} className="folha flex flex-col gap-5 p-6">
      <Campo
        rotulo="Versão do banco"
        ajuda="Identifica este banco dentro da sessão."
        value={versao}
        maxLength={50}
        onChange={(e) => setVersao(e.target.value)}
      />
      <div className="grid grid-cols-2 gap-3">
        <Campo
          rotulo="Questões objetivas"
          type="number"
          min={0}
          max={N_MAXIMO_BANCO}
          value={objetivas}
          onChange={(e) => setObjetivas(e.target.value)}
        />
        <Campo
          rotulo="Questões discursivas"
          type="number"
          min={0}
          max={N_MAXIMO_BANCO}
          value={discursivas}
          onChange={(e) => setDiscursivas(e.target.value)}
        />
      </div>
      <p
        className={`tabular font-grotesca text-detalhe ${
          totalValido ? "text-texto-suave" : "text-descartar"
        }`}
      >
        Total: {total ?? "—"}
        {!totalValido && ` — use de 1 a ${N_MAXIMO_BANCO} questões somando os dois tipos`}
      </p>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Cada questão leva cerca de 40 segundos. A geração acontece com esta janela
        aberta; se ela fechar, o que já foi gerado fica guardado e você continua depois.
      </p>
      <div className="flex justify-end">
        <Botao type="submit" disabled={!valido}>
          Gerar banco
        </Botao>
      </div>
    </form>
  );
}

function Progresso({
  acumulado,
  pausando,
  aoPausar,
}: {
  acumulado: Acumulado;
  pausando: boolean;
  aoPausar: () => void;
}) {
  const { ultimoNumero, total } = acumulado;
  return (
    <div className="cartao flex flex-col gap-3 p-6">
      <p className="font-serifa text-corpo-lg">
        {ultimoNumero === null
          ? "Gerando a primeira questão…"
          : `Questão ${ultimoNumero} de ${total} concluída`}
      </p>
      <progress
        className="w-full"
        aria-label="Progresso da geração"
        max={total}
        value={ultimoNumero ?? 0}
      />
      <div className="flex justify-end">
        <Botao variante="fantasma" disabled={pausando} onClick={aoPausar}>
          {pausando ? "Pausando depois desta questão…" : "Pausar geração"}
        </Botao>
      </div>
    </div>
  );
}

function SituacaoDoBanco({
  banco,
  sessaoId,
  aoContinuar,
}: {
  banco: MarcoBanco;
  sessaoId: string;
  aoContinuar: () => void;
}) {
  if (banco.lacunas === 0) {
    return (
      <div className="cartao flex flex-col gap-3 p-6">
        <p className="font-serifa text-corpo-lg">
          O banco {banco.versao} está completo, com {banco.n_atual}{" "}
          {questoes(banco.n_atual)}.
        </p>
        <div className="flex justify-end">
          <Link
            to="/sessoes/$sessaoId/banco"
            params={{ sessaoId }}
            className="botao botao-primario"
          >
            Seguir para a curadoria
          </Link>
        </div>
      </div>
    );
  }
  const lacunas = banco.lacunas;
  return (
    <div className="cartao flex flex-col gap-3 p-6">
      <p className="font-serifa text-corpo-lg">
        {lacunas === 1 ? "Falta" : "Faltam"} {lacunas} {questoes(lacunas)} no banco{" "}
        {banco.versao}.
      </p>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Continuar tenta de novo só os números sem questão. Você também pode seguir
        com as lacunas: o banco pode ser congelado assim.
      </p>
      <div className="flex flex-wrap justify-end gap-3">
        <Link
          to="/sessoes/$sessaoId/banco"
          params={{ sessaoId }}
          className="botao botao-fantasma"
        >
          Seguir para a curadoria com {lacunas} {lacunas === 1 ? "lacuna" : "lacunas"}
        </Link>
        <Botao onClick={aoContinuar}>Continuar geração</Botao>
      </div>
    </div>
  );
}

function Resumo({ acumulado }: { acumulado: Acumulado }) {
  const { geradas, improdutivas, comViolacoes } = acumulado;
  return (
    <section aria-label="Resumo da geração" className="cartao flex flex-col gap-3 p-6">
      <p className="font-serifa text-corpo-lg">
        {geradas} {geradas === 1 ? "questão gerada" : "questões geradas"} nesta rodada.
      </p>
      {improdutivas.length > 0 && (
        <Alerta variante="aviso" titulo="Sem sustentação no material">
          <p>
            Estes números ficaram sem questão, porque o material enviado não sustentou
            uma. Eles continuam como lacunas, e esta lista não é guardada.
          </p>
          <ul className="mt-2 list-disc pl-5">
            {improdutivas.map((i) => (
              <li key={i.numero}>
                Questão {i.numero} ({i.localizacao}): {i.motivo}
              </li>
            ))}
          </ul>
        </Alerta>
      )}
      {comViolacoes.length > 0 && (
        <p className="font-grotesca text-detalhe">
          {comViolacoes.length} {questoes(comViolacoes.length)} com violação de forma
          remanescente ({comViolacoes.map((v) => v.numero).join(", ")}). Você as verá
          na curadoria.
        </p>
      )}
    </section>
  );
}
