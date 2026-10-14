import { Link } from "@tanstack/react-router";
import type { Achado, MarcoBanco, Questao } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { formatarPercentual } from "../../lib/formatar";
import { CartaoQuestao } from "../banco/CartaoQuestao";
import { useMarcoSessao } from "../sessoes/api";
import { bancoMaisRecente } from "../sessoes/marco";
import { type Progresso, useAuditoriaEmLotes, useQuestoesDoBanco, useResumoAuditoria } from "./api";
import { ROTULO_RISCO } from "./rotulos";
import { TextoComFormulas } from "../../components/TextoComFormulas";

/** a auditoria do banco mais recente da sessão. M4 é comando, não marco. */
export function Auditoria({ sessaoId }: { sessaoId: string }) {
  const marco = useMarcoSessao(Number(sessaoId));
  const marcoBanco = marco.data ? bancoMaisRecente(marco.data) : null;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <h1 className="font-serifa text-titulo">Auditoria do banco</h1>

      {marco.isError && <Alerta variante="erro">{marco.error.message}</Alerta>}

      {marco.data && marcoBanco === null && (
        <Alerta variante="aviso">
          Esta sessão ainda não tem banco.{" "}
          <Link to="/sessoes/$sessaoId/geracao" params={{ sessaoId }} className="underline">
            Gerar banco
          </Link>
        </Alerta>
      )}

      {marcoBanco && marcoBanco.objetivas_ativas === 0 && (
        <Alerta variante="aviso">
          O banco {marcoBanco.versao} não tem objetivas ativas para auditar. As verificações
           são sobre alternativas, e discursivas não têm nenhuma.
        </Alerta>
      )}

      {marcoBanco && marcoBanco.objetivas_ativas > 0 && (
        <Corpo sessaoId={sessaoId} marcoBanco={marcoBanco} />
      )}

      <Link to="/sessoes/$sessaoId/banco" params={{ sessaoId }} className="font-grotesca text-detalhe underline">
        Voltar à curadoria
      </Link>
    </div>
  );
}

function Corpo({ sessaoId, marcoBanco }: { sessaoId: string; marcoBanco: MarcoBanco }) {
  const { banco_id: bancoId, objetivas_ativas: total, objetivas_auditadas: auditadas } = marcoBanco;
  const lote = useAuditoriaEmLotes(bancoId, Number(sessaoId));
  const resumo = useResumoAuditoria(bancoId);
  const banco = useQuestoesDoBanco(bancoId, marcoBanco.n_alvo);
  const rodando = lote.estado !== "parado";

  return (
    <>
      <p className="font-grotesca text-detalhe text-texto-suave">
        A auditoria confere, em cada objetiva ativa, se só uma alternativa é correta, se as
        erradas são defensáveis e se alguma destoa das outras em forma ou tamanho. Ela
        só aponta: nada é excluído, trocado ou reescrito sem você pedir. Cada questão leva
        cerca de 20 segundos, e a auditoria acontece com esta janela aberta; o que já foi
        auditado fica guardado e você continua depois.
      </p>

      {lote.erro && <Alerta variante="erro">{lote.erro.message}</Alerta>}

      {rodando && lote.progresso ? (
        <EmAndamento
          progresso={lote.progresso}
          pausando={lote.estado === "pausando"}
          aoPausar={lote.pausar}
        />
      ) : (
        <Situacao
          revisao={marcoBanco.revisao}
          auditadas={auditadas}
          total={total}
          aoAuditar={() => void lote.auditar(total, auditadas)}
        />
      )}

      {resumo.isError && <Alerta variante="erro">{resumo.error.message}</Alerta>}
      {banco.erro && <Alerta variante="erro">{banco.erro.message}</Alerta>}

      {resumo.data && resumo.data.auditadas > 0 && (
        <Resultado
          comAchado={resumo.data.questoes.length}
          auditadas={resumo.data.auditadas}
          proporcao={resumo.data.proporcao_com_achado}
          discursivasIgnoradas={resumo.data.discursivas_ignoradas}
        />
      )}

      {resumo.data && resumo.data.questoes.length > 0 && (
        <ul className="flex flex-col gap-6">
          {resumo.data.questoes.map(({ numero, achados }) => (
            <li key={numero}>
              <QuestaoComAchados
                numero={numero}
                achados={achados}
                questao={banco.questoes.find((q) => q.numero === numero && q.estado === "ativa")}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Situacao({
  revisao,
  auditadas,
  total,
  aoAuditar,
}: {
  revisao: number;
  auditadas: number;
  total: number;
  aoAuditar: () => void;
}) {
  const completa = auditadas >= total;
  return (
    <div className="cartao flex flex-wrap items-center justify-between gap-3 p-5">
      <p className="tabular font-serifa text-corpo-lg">
        {auditadas} de {total} objetivas auditadas na revisão r{revisao}
      </p>
      <Botao disabled={completa} onClick={aoAuditar}>
        {completa ? "Auditoria completa" : auditadas === 0 ? "Auditar objetivas" : "Continuar auditoria"}
      </Botao>
    </div>
  );
}

function EmAndamento({
  progresso,
  pausando,
  aoPausar,
}: {
  progresso: Progresso;
  pausando: boolean;
  aoPausar: () => void;
}) {
  return (
    <div className="cartao flex flex-col gap-3 p-5">
      <p className="tabular font-serifa text-corpo-lg">
        {progresso.auditadas} de {progresso.total} objetivas auditadas
      </p>
      <progress
        className="w-full"
        aria-label="Progresso da auditoria"
        max={progresso.total}
        value={progresso.auditadas}
      />
      <div className="flex justify-end">
        <Botao variante="fantasma" disabled={pausando} onClick={aoPausar}>
          {pausando ? "Pausando depois deste lote…" : "Pausar auditoria"}
        </Botao>
      </div>
    </div>
  );
}

function Resultado({
  comAchado,
  auditadas,
  proporcao,
  discursivasIgnoradas,
}: {
  comAchado: number;
  auditadas: number;
  proporcao: string;
  discursivasIgnoradas: number;
}) {
  return (
    <section aria-label="Resultado da auditoria" className="cartao flex flex-col gap-2 p-5">
      <p className="tabular font-serifa text-corpo-lg">
        {comAchado} de {auditadas} objetivas auditadas com achado ({formatarPercentual(proporcao)}%)
      </p>
      {/* a proporção é observação, nunca ordem de parar. */}
      <p className="font-grotesca text-detalhe text-texto-suave">
        É uma observação: quem decide o que fazer com cada achado é você, na curadoria.
      </p>
      {comAchado === 0 && (
        <p className="font-grotesca text-detalhe">
          Nenhum achado nas objetivas auditadas. Isso não garante que o banco esteja sem
          problemas: a auditoria é feita por um modelo local e pode deixar passar.
        </p>
      )}
      {discursivasIgnoradas > 0 && (
        <p className="font-grotesca text-detalhe">
          {discursivasIgnoradas} {discursivasIgnoradas === 1 ? "discursiva não foi auditada" : "discursivas não foram auditadas"}:
          as verificações são sobre alternativas.
        </p>
      )}
    </section>
  );
}

function QuestaoComAchados({
  numero,
  achados,
  questao,
}: {
  numero: number;
  achados: Achado[];
  questao: Questao | undefined;
}) {
  const apontadas = new Set(achados.map((a) => a.alvo));
  return (
    <div className="flex flex-col gap-3">
      {questao ? (
        <CartaoQuestao questao={questao} apontadas={apontadas} />
      ) : (
        <p className="font-serifa text-subtitulo">Questão {numero}</p>
      )}
      <section aria-label={`Achados da questão ${numero}`} className="flex flex-col gap-3">
        {achados.map((achado, i) => (
          <div key={i} className="cartao flex flex-col gap-2 p-4">
            <p className="font-grotesca font-semibold">{ROTULO_RISCO[achado.risco]}</p>
            <p className="font-grotesca text-detalhe">Alternativa apontada: {achado.alvo}</p>
            {achado.trecho_fonte && (
              <p className="font-grotesca text-detalhe text-texto-suave">
                Trecho que sustenta a concorrência ({achado.localizacao}): “{achado.trecho_fonte}”
              </p>
            )}
            <p className="font-grotesca text-detalhe">
              Orientação (o sistema não executa):{" "}
              <TextoComFormulas como="span" texto={achado.proposta_ajuste} />
            </p>
          </div>
        ))}
      </section>
    </div>
  );
}
