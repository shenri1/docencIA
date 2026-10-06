import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { ErroApi } from "../../api/erros";
import type { Marco, MarcoBanco } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { inteiroEntre } from "../../lib/validacao";
import { ROTULO_FAIXA, ROTULO_TIPO_QUESTAO } from "../banco/rotulos";
import { useMarcoSessao } from "../sessoes/api";
import { bancoMaisRecente } from "../sessoes/marco";
import { proximaAcao } from "../sessoes/proximaAcao";
import { useMontarProvas } from "./api";
import { VerProvas } from "./VerProvas";

// Do M10 em diante o banco já tem provas montadas.
const COM_PROVAS: ReadonlySet<Marco> = new Set<Marco>(["m10_docx", "concluido"]);
// Espelha N_MAXIMO_BANCO (backend/app/schemas/banco.py). Conveniência: a API
// continua sendo a autoridade.
const N_MAXIMO_PROVA = 25;
// o padrão de 10 questões por prova.
const N_PADRAO = 10;
const FAIXAS = ["facil", "media", "dificil"] as const;

/** a tela das provas do banco mais recente da sessão. */
export function Provas({ sessaoId }: { sessaoId: string }) {
  const id = Number(sessaoId);
  const marco = useMarcoSessao(id);
  const marcoBanco = marco.data ? bancoMaisRecente(marco.data) : null;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <h1 className="font-serifa text-titulo">Provas A e B</h1>

      {marco.isError && <Alerta variante="erro">{marco.error.message}</Alerta>}
      {marco.data && marcoBanco === null && (
        <Alerta variante="aviso">Esta sessão ainda não tem banco.</Alerta>
      )}
      {marco.data &&
        marcoBanco &&
        (COM_PROVAS.has(marcoBanco.marco) ? (
          <VerProvas bancoId={marcoBanco.banco_id} proxima={proximaAcao(marco.data)} />
        ) : marcoBanco.marco === "m6_provas" ? (
          <MontarProvas marcoBanco={marcoBanco} sessaoId={id} />
        ) : (
          <Alerta variante="aviso">
            {marcoBanco.motivo ??
              "Congele o banco na mesa de curadoria antes de montar as provas."}
          </Alerta>
        ))}

      <div className="flex flex-wrap gap-4 font-grotesca text-detalhe">
        <Link to="/sessoes/$sessaoId/banco" params={{ sessaoId }} className="underline">
          Voltar à mesa
        </Link>
        <Link to="/" className="underline">
          Voltar às sessões
        </Link>
      </div>
    </div>
  );
}

function MontarProvas({ marcoBanco, sessaoId }: { marcoBanco: MarcoBanco; sessaoId: number }) {
  const objetivasAtivas = marcoBanco.objetivas_ativas;
  const discursivasAtivas = marcoBanco.n_atual - objetivasAtivas;
  const [objetivas, setObjetivas] = useState(String(Math.min(N_PADRAO, objetivasAtivas)));
  const [discursivas, setDiscursivas] = useState("0");
  const [confirmando, setConfirmando] = useState(false);
  const montar = useMontarProvas(marcoBanco.banco_id, sessaoId);

  const o = inteiroEntre(objetivas, 0, N_MAXIMO_PROVA);
  const d = inteiroEntre(discursivas, 0, N_MAXIMO_PROVA);
  const total = o !== null && d !== null ? o + d : null;
  const valido = total !== null && total >= 1 && total <= N_MAXIMO_PROVA;

  function pedir(evento: FormEvent) {
    evento.preventDefault();
    if (valido) setConfirmando(true);
  }

  return (
    <form noValidate onSubmit={pedir} className="folha flex flex-col gap-5 p-6">
      <p className="font-grotesca text-detalhe">
        {`O banco ${marcoBanco.versao} tem ${objetivasAtivas} objetivas e ${discursivasAtivas} discursivas ativas.`}
      </p>
      {montar.error && <ErroMontagem erro={montar.error} />}
      <div className="grid grid-cols-2 gap-3">
        <Campo
          rotulo="Objetivas por prova"
          type="number"
          min={0}
          max={N_MAXIMO_PROVA}
          value={objetivas}
          onChange={(e) => {
            setObjetivas(e.target.value);
            setConfirmando(false);
          }}
        />
        <Campo
          rotulo="Discursivas por prova"
          type="number"
          min={0}
          max={N_MAXIMO_PROVA}
          value={discursivas}
          onChange={(e) => {
            setDiscursivas(e.target.value);
            setConfirmando(false);
          }}
        />
      </div>
      <p
        className={`tabular font-grotesca text-detalhe ${
          valido ? "text-texto-suave" : "text-descartar"
        }`}
      >
        Total por prova: {total ?? "—"}
        {!valido && ` — use de 1 a ${N_MAXIMO_PROVA} questões somando os dois tipos`}
      </p>
      {confirmando && o !== null && d !== null ? (
        <>
          <Alerta variante="aviso">
            {`Montar as provas A e B com ${o + d} questões cada? Depois de montar não é possível remontar nem aceitar variação.`}
          </Alerta>
          <div className="flex justify-end gap-3">
            <Botao variante="fantasma" onClick={() => setConfirmando(false)}>
              Cancelar
            </Botao>
            <Botao
              disabled={montar.isPending}
              onClick={() =>
                montar.mutate(
                  { n_objetivas: o, n_discursivas: d, revisao_esperada: marcoBanco.revisao },
                  { onSettled: () => setConfirmando(false) },
                )
              }
            >
              {montar.isPending ? "Montando…" : "Confirmar montagem"}
            </Botao>
          </div>
        </>
      ) : (
        <div className="flex justify-end">
          <Botao type="submit" disabled={!valido}>
            Montar provas
          </Botao>
        </div>
      )}
    </form>
  );
}

/** 409 é orientação, não falha; 500 é erro do sistema. */
function ErroMontagem({ erro }: { erro: Error }) {
  const api = erro instanceof ErroApi ? erro : null;
  return (
    <Alerta variante={api?.status === 409 ? "aviso" : "erro"}>
      <p>{erro.message}</p>
      {api?.codigo === "BANCO_INSUFICIENTE_PARA_PROVA" && (
        <TabelaInsuficiencia extras={api.extras} />
      )}
    </Alerta>
  );
}

function contagens(valor: unknown): Record<string, number> {
  if (typeof valor !== "object" || valor === null) return {};
  return Object.fromEntries(
    Object.entries(valor).filter((par): par is [string, number] => typeof par[1] === "number"),
  );
}

function TabelaInsuficiencia({ extras }: { extras: Record<string, unknown> }) {
  const pedido = contagens(extras.pedido_por_tipo);
  const cotas = contagens(extras.cotas_por_faixa);
  const disponivel = contagens(extras.disponivel_por_celula);
  return (
    <div className="mt-2 flex flex-col gap-2">
      <p className="tabular">
        {`Cada prova pede ${pedido.objetiva ?? 0} objetivas e ${pedido.discursiva ?? 0} discursivas; por faixa: ${FAIXAS.map(
          (f) => `${ROTULO_FAIXA[f].toLowerCase()} ${cotas[f] ?? 0}`,
        ).join(" · ")}.`}
      </p>
      <table className="tabular">
        <caption className="text-left font-semibold">Questões ativas no banco</caption>
        <thead>
          <tr>
            <th className="pr-4 text-left">Tipo</th>
            {FAIXAS.map((f) => (
              <th key={f} className="pr-4 text-left">
                {ROTULO_FAIXA[f]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(["objetiva", "discursiva"] as const).map((tipo) => (
            <tr key={tipo}>
              <td className="pr-4">{ROTULO_TIPO_QUESTAO[tipo]}</td>
              {FAIXAS.map((f) => (
                <td key={f} className="pr-4">
                  {disponivel[`${tipo}/${f}`] ?? 0}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
