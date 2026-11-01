import type { ReactNode } from "react";
import type { Orientacao, Questao } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { IconeAviso, IconeErro, IconeInfo, IconeOk } from "../../components/Icones";
import { textoOrientacao } from "../orientacoes/texto";
import { ListaAspectos } from "./ListaAspectos";
import { ROTULO_BLOOM, ROTULO_FAIXA, ROTULO_FORMATO, ROTULO_TIPO_QUESTAO } from "./rotulos";
import { TextoComFormulas } from "../../components/TextoComFormulas";

type FonteQuestao = Questao["fontes"][number];

// Estado sempre com ícone e texto, nunca só cor.
const ESTADO: Record<
  Questao["estado"] | "marcada",
  { rotulo: string; Icone: () => ReactNode; cor: string }
> = {
  ativa: { rotulo: "Ativa", Icone: IconeOk, cor: "text-manter" },
  marcada: { rotulo: "Marcada para exclusão", Icone: IconeErro, cor: "text-descartar" },
  excluida: { rotulo: "Excluída", Icone: IconeErro, cor: "text-descartar" },
  substituida: { rotulo: "Substituída", Icone: IconeInfo, cor: "text-texto-suave" },
  candidata: { rotulo: "Variação proposta", Icone: IconeInfo, cor: "text-aviso" },
  descartada: { rotulo: "Variação descartada", Icone: IconeInfo, cor: "text-texto-suave" },
};

interface Props {
  questao: Questao;
  /** Marcada para exclusão e ainda não aplicada: só a mesa sabe disso. */
  marcada?: boolean;
  /** Botões da mesa; o cartão só exibe e não decide nada. */
  acoes?: ReactNode;
  /** Letras que a auditoria apontou nesta questão. */
  apontadas?: ReadonlySet<string>;
  /** as orientações vigentes na geração, já resolvidas pelos ids. */
  orientacoes?: readonly Orientacao[];
}

export function CartaoQuestao({ questao, marcada = false, acoes, apontadas, orientacoes }: Props) {
  const estado = ESTADO[marcada ? "marcada" : questao.estado];
  const nome =
    questao.estado === "candidata"
      ? `Variação proposta para a questão ${questao.numero}`
      : `Questão ${questao.numero}`;

  return (
    <article
      aria-label={nome}
      className={`cartao flex flex-col gap-4 p-5 ${marcada ? "border-descartar" : ""}`}
    >
      <header className="flex flex-wrap items-center gap-2 font-grotesca text-detalhe">
        <span className="tabular font-serifa text-subtitulo">{questao.numero}</span>
        <span className="chip">{ROTULO_TIPO_QUESTAO[questao.tipo]}</span>
        {ROTULO_FORMATO[questao.formato] && (
          <span className="chip">{ROTULO_FORMATO[questao.formato]}</span>
        )}
        <span className="chip">{ROTULO_FAIXA[questao.faixa_dificuldade]}</span>
        <span className="chip">{ROTULO_BLOOM[questao.nivel_bloom]}</span>
        {questao.tema && <span className="text-texto-suave">{questao.tema}</span>}
        <span className={`chip ml-auto flex items-center gap-1 ${estado.cor}`}>
          <estado.Icone />
          {estado.rotulo}
        </span>
      </header>

      <TextoComFormulas className="font-serifa text-corpo-lg" texto={questao.enunciado} />

      {questao.tipo === "objetiva" ? (
        <ol className="flex flex-col gap-2">
          {questao.alternativas.map(({ letra, texto }) => {
            const correta = letra === questao.letra_correta;
            return (
              <li
                key={letra}
                className={`flex flex-wrap gap-2 font-serifa ${correta ? "font-semibold text-manter" : ""}`}
              >
                <span className="tabular">{letra})</span>
                <TextoComFormulas como="span" texto={texto} />
                {correta && (
                  <span className="flex items-center gap-1 font-grotesca text-detalhe">
                    <IconeOk />
                    Correta
                  </span>
                )}
                {apontadas?.has(letra) && (
                  <span className="flex items-center gap-1 font-grotesca text-detalhe text-aviso">
                    <IconeAviso />
                    Apontada pela auditoria
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="flex flex-col gap-2">
          <h3 className="font-grotesca text-detalhe font-semibold">Aspectos esperados</h3>
          <ListaAspectos
            aspectos={questao.aspectos_esperados}
            fonte={(aspecto) => <TrechoFonte fonte={aspecto.fonte} />}
          />
        </div>
      )}

      {questao.violacoes.length > 0 && (
        <Alerta variante="aviso" titulo="Avisos de forma que a revisão não resolveu">
          <ul>
            {questao.violacoes.map((violacao, i) => (
              <li key={i}>
                {violacao.detalhe} ({violacao.alvo})
              </li>
            ))}
          </ul>
        </Alerta>
      )}

      {orientacoes && orientacoes.length > 0 && (
        <p className="font-grotesca text-detalhe text-texto-suave">
          Orientações: {orientacoes.map(textoOrientacao).join("; ")}
        </p>
      )}

      <details className="font-grotesca text-detalhe">
        <summary className="cursor-pointer">Fontes ({questao.fontes.length})</summary>
        <ul className="mt-2 flex flex-col gap-2">
          {questao.fontes.map((fonte, i) => (
            <li key={i}>
              <TrechoFonte fonte={fonte} />
            </li>
          ))}
        </ul>
      </details>

      {acoes && <div className="flex flex-wrap items-start justify-end gap-3">{acoes}</div>}
    </article>
  );
}

function TrechoFonte({ fonte }: { fonte: FonteQuestao }) {
  return (
    <p className="font-grotesca text-detalhe text-texto-suave">
      {fonte.identificador_material}, {fonte.localizacao}: “{fonte.trecho_base}”
    </p>
  );
}
