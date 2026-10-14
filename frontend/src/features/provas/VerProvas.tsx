import { Link } from "@tanstack/react-router";
import type { ProvasMontadas } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { ROTULO_FAIXA, ROTULO_TIPO_QUESTAO } from "../banco/rotulos";
import { useProva, useProvasDoBanco } from "./api";
import { TextoComFormulas } from "../../components/TextoComFormulas";

/** M10: verificação e as duas provas lado a lado. */
export function VerProvas({
  bancoId,
  sessaoId,
  proxima,
}: {
  bancoId: number;
  sessaoId: string;
  proxima: string;
}) {
  const montadas = useProvasDoBanco(bancoId);

  if (montadas.isError) return <Alerta variante="erro">{montadas.error.message}</Alerta>;
  if (!montadas.data) {
    return <p className="font-grotesca text-detalhe text-texto-suave">Carregando as provas…</p>;
  }
  const dados = montadas.data;
  const compartilhadas = new Set(dados.compartilhadas);

  return (
    <>
      <p className="tabular font-grotesca text-detalhe">
        Montadas sobre a revisão r{dados.revisao_banco} do banco.
      </p>
      <Verificacao montadas={dados} />
      <div className="grid gap-6 md:grid-cols-2">
        <ColunaProva provaId={dados.prova_a_id} outra="B" compartilhadas={compartilhadas} />
        <ColunaProva provaId={dados.prova_b_id} outra="A" compartilhadas={compartilhadas} />
      </div>
      <Alerta>
        Próxima ação:{" "}
        <Link to="/sessoes/$sessaoId/entrega" params={{ sessaoId }} className="underline">
          {proxima}
        </Link>
      </Alerta>
    </>
  );
}

function Verificacao({ montadas }: { montadas: ProvasMontadas }) {
  const v = montadas.verificacao;
  const subtemas = Object.entries(v.subtemas_compartilhados);
  return (
    <section aria-label="Verificação das provas" className="flex flex-col gap-3">
      {v.violacoes.length === 0 ? (
        <Alerta variante="sucesso" titulo="Verificação sem violações">
          {`${v.colisoes_letras} colisões de letra em ${v.posicoes_objetivas} posições objetivas; ${v.compartilhadas} questões compartilhadas`}
          {subtemas.length > 0 &&
            `; subtemas compartilhados: ${subtemas.map(([s, n]) => `${s} (${n})`).join(", ")}`}
          .
        </Alerta>
      ) : (
        <Alerta variante="aviso" titulo="A verificação encontrou violações">
          <ul>
            {v.violacoes.map((violacao) => (
              <li key={violacao}>{violacao}</li>
            ))}
          </ul>
        </Alerta>
      )}
      {montadas.sem_subtema > 0 && (
        <Alerta variante="aviso">
          {`${montadas.sem_subtema} ${montadas.sem_subtema === 1 ? "questão não tem": "questões não têm"} subtema. A regra de sobreposição de subtema não as enxerga, então essa parte da verificação é parcial.`}
        </Alerta>
      )}
    </section>
  );
}

function ColunaProva({
  provaId,
  outra,
  compartilhadas,
}: {
  provaId: number;
  outra: "A" | "B";
  compartilhadas: ReadonlySet<number>;
}) {
  const prova = useProva(provaId);

  if (prova.isError) return <Alerta variante="erro">{prova.error.message}</Alerta>;
  if (!prova.data) {
    return <p className="font-grotesca text-detalhe text-texto-suave">Carregando a prova…</p>;
  }
  const p = prova.data;

  return (
    <section aria-label={`Prova ${p.versao}`} className="flex flex-col gap-4">
      <h2 className="font-serifa text-subtitulo">Prova {p.versao}</h2>
      <p className="tabular font-grotesca text-detalhe text-texto-suave">
        {`${p.n_questoes} questões: ${p.n_objetivas} objetivas e ${p.n_discursivas} discursivas`}
      </p>
      {p.desatualizada && (
        <Alerta variante="aviso">
          {`O banco mudou desde a montagem: a prova foi montada na revisão r${p.revisao_banco} e o banco está na r${p.banco_revisao_atual}.`}
        </Alerta>
      )}
      <ol className="flex flex-col gap-3">
        {p.itens.map((item) => (
          <li key={item.posicao}>
            <article
              aria-label={`Prova ${p.versao}, posição ${item.posicao}`}
              className="cartao flex flex-col gap-3 p-4"
            >
              <header className="flex flex-wrap items-center gap-2 font-grotesca text-detalhe">
                <span className="tabular font-serifa text-subtitulo">{item.posicao}</span>
                <span className="chip">{ROTULO_TIPO_QUESTAO[item.tipo]}</span>
                <span className="chip">{ROTULO_FAIXA[item.faixa_dificuldade]}</span>
                <span className="tabular text-texto-suave">Questão {item.numero} do banco</span>
                {compartilhadas.has(item.numero) && (
                  <span className="chip ml-auto">Também na Prova {outra}</span>
                )}
              </header>
              <TextoComFormulas className="font-serifa text-corpo-lg" texto={item.enunciado} />
              {item.alternativas.length > 0 && (
                <ol className="flex flex-col gap-1 font-serifa">
                  {item.alternativas.map((alternativa) => (
                    <li key={alternativa.letra} className="flex gap-2">
                      <span className="tabular">{alternativa.letra})</span>
                      <TextoComFormulas como="span" texto={alternativa.texto} />
                    </li>
                  ))}
                </ol>
              )}
            </article>
          </li>
        ))}
      </ol>
    </section>
  );
}
