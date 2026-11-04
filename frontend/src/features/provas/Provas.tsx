import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { ErroApi } from "../../api/erros";
import type { Marco, MarcoBanco, Questao } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { TextoComFormulas } from "../../components/TextoComFormulas";
import { inteiroEntre } from "../../lib/validacao";
import { ROTULO_FAIXA, ROTULO_TIPO_QUESTAO } from "../banco/rotulos";
import { useMarcoSessao } from "../sessoes/api";
import { bancoMaisRecente } from "../sessoes/marco";
import { proximaAcao } from "../sessoes/proximaAcao";
import { useMontarProvas, useQuestoesDoBanco, useSugerirSelecao } from "./api";
import { VerProvas } from "./VerProvas";

// Do M10 em diante o banco já tem provas montadas.
const COM_PROVAS: ReadonlySet<Marco> = new Set<Marco>(["m10_docx", "concluido"]);
// Espelha N_MAXIMO_BANCO (backend/app/schemas/banco.py). Conveniência: a API
// continua sendo a autoridade.
const N_MAXIMO_PROVA = 25;
// O padrão de 10 questões por prova.
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
          <VerProvas bancoId={marcoBanco.banco_id} sessaoId={sessaoId} proxima={proximaAcao(marco.data)} />
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
        <Link to="/sessoes" className="underline">
          Voltar às sessões
        </Link>
      </div>
    </div>
  );
}

type Versao = "A" | "B";

function MontarProvas({ marcoBanco, sessaoId }: { marcoBanco: MarcoBanco; sessaoId: number }) {
  const objetivasAtivas = marcoBanco.objetivas_ativas;
  const discursivasAtivas = marcoBanco.n_atual - objetivasAtivas;
  const banco = useQuestoesDoBanco(marcoBanco.banco_id, N_MAXIMO_PROVA);
  const ativas = (banco.data?.questoes ?? []).filter((q) => q.estado === "ativa");
  const [marcadas, setMarcadas] = useState<Record<Versao, ReadonlySet<number>>>({
    A: new Set(),
    B: new Set(),
  });
  const [objetivas, setObjetivas] = useState(String(Math.min(N_PADRAO, objetivasAtivas)));
  const [discursivas, setDiscursivas] = useState("0");
  const [confirmando, setConfirmando] = useState(false);
  const sugerir = useSugerirSelecao(marcoBanco.banco_id);
  const montar = useMontarProvas(marcoBanco.banco_id, sessaoId);

  const o = inteiroEntre(objetivas, 0, N_MAXIMO_PROVA);
  const d = inteiroEntre(discursivas, 0, N_MAXIMO_PROVA);
  const totalSugestao = o !== null && d !== null ? o + d : null;
  const sugestaoValida =
    totalSugestao !== null && totalSugestao >= 1 && totalSugestao <= N_MAXIMO_PROVA;

  const tamanho = (v: Versao) => marcadas[v].size;
  const valida = (v: Versao) => tamanho(v) >= 1 && tamanho(v) <= N_MAXIMO_PROVA;
  const emComum = [...marcadas.A].filter((n) => marcadas.B.has(n)).length;

  function alternar(numero: number, versao: Versao) {
    setConfirmando(false);
    setMarcadas((atual) => {
      const novo = new Set(atual[versao]);
      if (novo.has(numero)) novo.delete(numero);
      else novo.add(numero);
      return { ...atual, [versao]: novo };
    });
  }

  function pedirSugestao() {
    if (o === null || d === null) return;
    setConfirmando(false);
    sugerir.mutate(
      { n_objetivas: o, n_discursivas: d },
      {
        onSuccess: (s) => setMarcadas({ A: new Set(s.numeros_a), B: new Set(s.numeros_b) }),
      },
    );
  }

  function pedir(evento: FormEvent) {
    evento.preventDefault();
    if (valida("A") && valida("B")) setConfirmando(true);
  }

  const ordenados = (v: Versao) => [...marcadas[v]].sort((x, y) => x - y);
  const erro = montar.error ?? sugerir.error;

  return (
    <form noValidate onSubmit={pedir} className="folha flex flex-col gap-5 p-6">
      <p className="font-grotesca text-detalhe">
        {`O banco ${marcoBanco.versao} tem ${objetivasAtivas} objetivas e ${discursivasAtivas} discursivas ativas.`}
      </p>
      <p className="font-grotesca text-detalhe text-texto-suave">
        Marque o que vai para cada prova. A mesma questão pode ir para as duas.
      </p>
      {erro && <ErroMontagem erro={erro} />}

      <fieldset className="flex flex-col gap-3">
        <legend className="font-grotesca text-detalhe font-semibold">Sugestão automática</legend>
        <div className="grid grid-cols-2 gap-3">
          <Campo
            rotulo="Objetivas por prova"
            type="number"
            min={0}
            max={N_MAXIMO_PROVA}
            value={objetivas}
            onChange={(e) => setObjetivas(e.target.value)}
          />
          <Campo
            rotulo="Discursivas por prova"
            type="number"
            min={0}
            max={N_MAXIMO_PROVA}
            value={discursivas}
            onChange={(e) => setDiscursivas(e.target.value)}
          />
        </div>
        <div className="flex justify-end gap-3">
          <Botao
            variante="fantasma"
            onClick={() => {
              setConfirmando(false);
              setMarcadas({ A: new Set(), B: new Set() });
            }}
          >
            Limpar
          </Botao>
          <Botao
            variante="fantasma"
            disabled={!sugestaoValida || sugerir.isPending}
            onClick={pedirSugestao}
          >
            {sugerir.isPending ? "Sugerindo…" : "Sugerir seleção"}
          </Botao>
        </div>
      </fieldset>

      {banco.isError && <Alerta variante="erro">{banco.error.message}</Alerta>}
      {banco.isPending && <p className="font-grotesca text-detalhe">Carregando questões…</p>}
      {ativas.length > 0 && (
        <table className="tabular w-full font-grotesca text-detalhe">
          <caption className="sr-only">Questões do banco</caption>
          <thead>
            <tr className="border-b border-borda text-left">
              <th scope="col" className="py-2 pr-3">Nº</th>
              <th scope="col" className="py-2 pr-3">Questão</th>
              <th scope="col" className="py-2 pr-3">Prova A</th>
              <th scope="col" className="py-2">Prova B</th>
            </tr>
          </thead>
          <tbody>
            {ativas.map((q) => (
              <tr key={q.numero} className="border-b border-borda align-top">
                <td className="py-2 pr-3">{q.numero}</td>
                <td className="py-2 pr-3">
                  <span className="text-texto-suave">
                    {`${ROTULO_TIPO_QUESTAO[q.tipo]} · ${ROTULO_FAIXA[q.faixa_dificuldade]}${
                      q.tema ? ` · ${q.tema}` : ""
                    }`}
                  </span>
                  <TextoComFormulas texto={q.enunciado} className="line-clamp-2 font-serifa text-corpo" />
                </td>
                {(["A", "B"] as const).map((v) => (
                  <td key={v} className="py-2 pr-3">
                    <input
                      type="checkbox"
                      className="caixa"
                      aria-label={`Questão ${q.numero} na Prova ${v}`}
                      checked={marcadas[v].has(q.numero)}
                      onChange={() => alternar(q.numero, v)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex flex-col gap-1 font-grotesca text-detalhe">
        {(["A", "B"] as const).map((v) => (
          <p key={v} className={`tabular ${valida(v) ? "text-texto-suave" : "text-descartar"}`}>
            {resumo(v, ativas.filter((q) => marcadas[v].has(q.numero)))}
          </p>
        ))}
        {emComum > 0 && (
          <p className="tabular text-texto-suave">
            {emComum === 1 ? "1 questão nas duas provas." : `${emComum} questões nas duas provas.`}
          </p>
        )}
      </div>

      {confirmando ? (
        <>
          <Alerta variante="aviso">
            {`Montar a Prova A com ${tamanho("A")} questões e a Prova B com ${tamanho("B")} questões? Depois de montar não é possível remontar nem aceitar variação.`}
          </Alerta>
          <div className="flex justify-end gap-3">
            <Botao variante="fantasma" onClick={() => setConfirmando(false)}>
              Cancelar
            </Botao>
            <Botao
              disabled={montar.isPending}
              onClick={() =>
                montar.mutate(
                  {
                    numeros_a: ordenados("A"),
                    numeros_b: ordenados("B"),
                    revisao_esperada: marcoBanco.revisao,
                  },
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
          <Botao type="submit" disabled={!valida("A") || !valida("B")}>
            Montar provas
          </Botao>
        </div>
      )}
    </form>
  );
}

/** Contagem por tipo e faixa. Só informa: a proporção vale na geração do banco. */
function resumo(versao: Versao, questoes: Questao[]): string {
  const n = questoes.length;
  if (n === 0) return `Prova ${versao}: nenhuma questão marcada`;
  const obj = questoes.filter((q) => q.tipo === "objetiva").length;
  const porFaixa = FAIXAS.map(
    (f) => `${ROTULO_FAIXA[f].toLowerCase()} ${questoes.filter((q) => q.faixa_dificuldade === f).length}`,
  ).join(" · ");
  const excesso = n > N_MAXIMO_PROVA ? ` — no máximo ${N_MAXIMO_PROVA}` : "";
  return `Prova ${versao}: ${n} ${n === 1 ? "questão" : "questões"} (${obj} objetivas, ${n - obj} discursivas) · ${porFaixa}${excesso}`;
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
            <th scope="col" className="pr-4 text-left">Tipo</th>
            {FAIXAS.map((f) => (
              <th key={f} scope="col" className="pr-4 text-left">
                {ROTULO_FAIXA[f]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(["objetiva", "discursiva"] as const).map((tipo) => (
            <tr key={tipo}>
              <th scope="row" className="pr-4 text-left font-normal">
                {ROTULO_TIPO_QUESTAO[tipo]}
              </th>
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
