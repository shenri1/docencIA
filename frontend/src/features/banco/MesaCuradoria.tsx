import { Link } from "@tanstack/react-router";
import { useState } from "react";
import type { Banco, MarcoBanco, Questao, RelatorioImpacto as Relatorio } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { useMarcoSessao } from "../sessoes/api";
import { bancoMaisRecente } from "../sessoes/marco";
import { proximaAcao } from "../sessoes/proximaAcao";
import { CartaoQuestao } from "./CartaoQuestao";
import { mensagemDeErro, TAMANHO_BLOCO, useBanco, useCongelar, useExcluir } from "./curadoria";
import { RelatorioImpacto } from "./RelatorioImpacto";
import { Comparacao, PedirVariacao } from "./Variacao";

/** a mesa do banco mais recente da sessão. */
export function MesaCuradoria({ sessaoId }: { sessaoId: string }) {
  const id = Number(sessaoId);
  const marco = useMarcoSessao(id);
  const marcoBanco = marco.data ? bancoMaisRecente(marco.data) : null;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <h1 className="font-serifa text-titulo">Banco de questões</h1>

      {marco.isError && <Alerta variante="erro">{marco.error.message}</Alerta>}

      {marco.data && marcoBanco === null && (
        <Alerta variante="aviso">
          Esta sessão ainda não tem banco.{" "}
          <Link to="/sessoes/$sessaoId/geracao" params={{ sessaoId }} className="underline">
            Gerar banco
          </Link>
        </Alerta>
      )}

      {marco.data && marcoBanco && (
        <Mesa sessaoId={id} marcoBanco={marcoBanco} proxima={proximaAcao(marco.data)} />
      )}

      <Link to="/" className="font-grotesca text-detalhe underline">
        Voltar às sessões
      </Link>
    </div>
  );
}

interface MesaProps {
  sessaoId: number;
  marcoBanco: MarcoBanco;
  proxima: string;
}

function Mesa({ sessaoId, marcoBanco, proxima }: MesaProps) {
  const [pagina, setPagina] = useState(1);
  const [historico, setHistorico] = useState(false);
  // locais à tela — sobrevivem à troca de bloco, somem ao recarregar.
  const [marcadas, setMarcadas] = useState<ReadonlySet<number>>(new Set());
  const [aviso, setAviso] = useState<string | null>(null);
  const banco = useBanco(marcoBanco.banco_id, pagina);

  if (banco.isError) return <Alerta variante="erro">{banco.error.message}</Alerta>;
  if (!banco.data) {
    return <p className="font-grotesca text-detalhe text-texto-suave">Carregando o banco…</p>;
  }
  const dados = banco.data;
  const visiveis = dados.questoes.filter((q) =>
    historico ? q.estado !== "candidata" : q.estado === "ativa",
  );
  // A candidata vem na mesma leitura (histórico) e aparece junto da original.
  const candidatas = new Map(
    dados.questoes.filter((q) => q.estado === "candidata").map((q) => [q.numero, q]),
  );
  // do M10 em diante já há prova montada, e a API recusaria o aceite.
  const podeVariar = marcoBanco.marco === "m3_exclusoes" || marcoBanco.marco === "m6_provas";
  const provasMontadas = marcoBanco.marco === "m10_docx" || marcoBanco.marco === "concluido";

  function alternar(numero: number) {
    setMarcadas((atual) => {
      const nova = new Set(atual);
      if (nova.has(numero)) nova.delete(numero);
      else nova.add(numero);
      return nova;
    });
  }

  function aplicadas(relatorio: Relatorio) {
    setMarcadas(new Set());
    setAviso(
      `Exclusões aplicadas. O banco está na revisão r${relatorio.revisao}, com ${relatorio.n_final} questões ativas.`,
    );
  }

  return (
    <>
      <Painel banco={dados} lacunas={marcoBanco.lacunas} />
      {aviso && <Alerta variante="sucesso">{aviso}</Alerta>}
      {provasMontadas && (
        <Alerta>
          As provas já foram montadas sobre este banco. Uma variação aceita agora as deixaria
          desatualizadas, por isso não é possível pedir variação.
        </Alerta>
      )}
      {dados.estado === "congelado" && (
        <Alerta titulo="Banco congelado">
          A janela de exclusões está fechada. Próxima ação: {proxima} — ainda não disponível
          nesta versão da interface.
        </Alerta>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Blocos nAlvo={dados.n_alvo} pagina={pagina} aoMudar={setPagina} />
        <label className="flex items-center gap-2 font-grotesca text-detalhe">
          <input
            type="checkbox"
            checked={historico}
            onChange={(e) => setHistorico(e.target.checked)}
          />
          Mostrar excluídas e substituídas
        </label>
      </div>

      <ul className="flex flex-col gap-4">
        {/* Índice na chave: com histórico, o mesmo número aparece mais de uma vez. */}
        {visiveis.map((questao, i) => (
          <li key={`${questao.numero}-${i}`}>
            <ItemDaMesa
              questao={questao}
              banco={dados}
              sessaoId={sessaoId}
              candidata={questao.estado === "ativa" ? candidatas.get(questao.numero) : undefined}
              podeVariar={podeVariar}
              marcada={questao.estado === "ativa" && marcadas.has(questao.numero)}
              aoAlternar={() => alternar(questao.numero)}
              aoConcluir={setAviso}
            />
          </li>
        ))}
      </ul>

      {marcadas.size > 0 && (
        <BarraExclusoes
          banco={dados}
          sessaoId={sessaoId}
          marcadas={marcadas}
          aoAplicar={aplicadas}
        />
      )}

      {dados.estado === "aberto" && (
        <Congelar
          banco={dados}
          sessaoId={sessaoId}
          pendentes={marcadas.size}
          aoCongelar={(relatorio) =>
            setAviso(
              `Banco congelado na revisão r${relatorio.revisao}, com ${relatorio.n_final} questões ativas.`,
            )
          }
        />
      )}
    </>
  );
}

interface ItemProps {
  questao: Questao;
  banco: Banco;
  sessaoId: number;
  /** Candidata pendente para o mesmo número, se houver. */
  candidata: Questao | undefined;
  podeVariar: boolean;
  marcada: boolean;
  aoAlternar: () => void;
  aoConcluir: (texto: string) => void;
}

function ItemDaMesa({
  questao,
  banco,
  sessaoId,
  candidata,
  podeVariar,
  marcada,
  aoAlternar,
  aoConcluir,
}: ItemProps) {
  if (candidata) {
    return (
      <Comparacao
        banco={banco}
        sessaoId={sessaoId}
        original={questao}
        candidata={candidata}
        aoConcluir={aoConcluir}
      />
    );
  }
  const ativa = questao.estado === "ativa";
  const podeMarcar = ativa && banco.estado === "aberto";
  const variar = ativa && podeVariar;
  return (
    <CartaoQuestao
      questao={questao}
      marcada={marcada}
      acoes={
        podeMarcar || variar ? (
          <>
            {variar && (
              <PedirVariacao bancoId={banco.banco_id} sessaoId={sessaoId} numero={questao.numero} />
            )}
            {podeMarcar &&
              (marcada ? (
                <Botao variante="manter" onClick={aoAlternar}>
                  Manter
                </Botao>
              ) : (
                <Botao variante="descartar" onClick={aoAlternar}>
                  Marcar para exclusão
                </Botao>
              ))}
          </>
        ) : undefined
      }
    />
  );
}

function BarraExclusoes({
  banco,
  sessaoId,
  marcadas,
  aoAplicar,
}: {
  banco: Banco;
  sessaoId: number;
  marcadas: ReadonlySet<number>;
  aoAplicar: (relatorio: Relatorio) => void;
}) {
  const excluir = useExcluir(banco.banco_id, sessaoId);
  const [confirmando, setConfirmando] = useState(false);
  const numeros = [...marcadas].sort((a, b) => a - b);
  const uma = numeros.length === 1;

  return (
    <div className="folha sticky bottom-4 flex flex-col gap-3 p-4">
      {excluir.error && <Alerta variante="erro">{mensagemDeErro(excluir.error)}</Alerta>}
      {confirmando ? (
        <>
          <p className="font-grotesca text-detalhe">
            Excluir {uma ? "a questão" : "as questões"} {numeros.join(", ")}? O banco ganha
            uma revisão nova, e {uma ? "a excluída continua visível" : "as excluídas continuam visíveis"} no histórico.
          </p>
          <div className="flex justify-end gap-3">
            <Botao variante="fantasma" onClick={() => setConfirmando(false)}>
              Cancelar
            </Botao>
            <Botao
              variante="descartar"
              disabled={excluir.isPending}
              onClick={() =>
                excluir.mutate(
                  { numeros, revisao_esperada: banco.revisao },
                  { onSuccess: aoAplicar, onSettled: () => setConfirmando(false) },
                )
              }
            >
              {excluir.isPending ? "Aplicando…" : "Confirmar exclusões"}
            </Botao>
          </div>
        </>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="tabular font-grotesca text-detalhe">
            {numeros.length} {uma ? "marcada" : "marcadas"} para exclusão
          </p>
          <Botao variante="descartar" onClick={() => setConfirmando(true)}>
            Aplicar exclusões
          </Botao>
        </div>
      )}
    </div>
  );
}

function Painel({ banco, lacunas }: { banco: Banco; lacunas: number }) {
  return (
    <section aria-label="Situação do banco" className="cartao flex flex-col gap-3 p-5">
      <p className="flex flex-wrap gap-x-4 gap-y-1 font-grotesca text-detalhe">
        <span className="tabular font-semibold">{banco.rotulo}</span>
        <span>{banco.estado === "aberto" ? "Aberto para exclusões" : "Congelado"}</span>
        <span className="tabular">
          {banco.n_atual} de {banco.n_alvo} questões ativas
        </span>
        {lacunas > 0 && (
          <span className="tabular">
            {lacunas} {lacunas === 1 ? "lacuna" : "lacunas"}
          </span>
        )}
      </p>
      {banco.ultimo_relatorio && <RelatorioImpacto relatorio={banco.ultimo_relatorio} />}
    </section>
  );
}

function Blocos({
  nAlvo,
  pagina,
  aoMudar,
}: {
  nAlvo: number;
  pagina: number;
  aoMudar: (pagina: number) => void;
}) {
  const total = Math.max(1, Math.ceil(nAlvo / TAMANHO_BLOCO));
  if (total === 1) return <span />;
  return (
    <nav aria-label="Blocos de questões" className="flex gap-2">
      {Array.from({ length: total }, (_, i) => i + 1).map((p) => (
        <Botao
          key={p}
          variante={p === pagina ? "primario" : "fantasma"}
          aria-pressed={p === pagina}
          onClick={() => aoMudar(p)}
        >
          {(p - 1) * TAMANHO_BLOCO + 1}–{Math.min(p * TAMANHO_BLOCO, nAlvo)}
        </Botao>
      ))}
    </nav>
  );
}

function Congelar({
  banco,
  sessaoId,
  pendentes,
  aoCongelar,
}: {
  banco: Banco;
  sessaoId: number;
  pendentes: number;
  aoCongelar: (relatorio: Relatorio) => void;
}) {
  const congelar = useCongelar(banco.banco_id, sessaoId);
  const [confirmando, setConfirmando] = useState(false);

  return (
    <section aria-label="Congelar banco" className="cartao flex flex-col gap-3 p-5">
      {congelar.error && <Alerta variante="erro">{mensagemDeErro(congelar.error)}</Alerta>}
      {/* congelar descartaria as marcações em silêncio. */}
      {pendentes > 0 && (
        <p className="font-grotesca text-detalhe text-texto-suave">
          {pendentes === 1
            ? "Aplique ou desmarque a exclusão marcada antes de congelar."
            : `Aplique ou desmarque as ${pendentes} exclusões marcadas antes de congelar.`}
        </p>
      )}
      {confirmando ? (
        <>
          <Alerta variante="aviso">
            Congelar o banco {banco.rotulo}? Isso fecha a janela de exclusões e não pode ser
            desfeito. Pedir variação continua possível.
          </Alerta>
          <div className="flex justify-end gap-3">
            <Botao variante="fantasma" onClick={() => setConfirmando(false)}>
              Cancelar
            </Botao>
            <Botao
              disabled={congelar.isPending}
              onClick={() =>
                congelar.mutate(banco.revisao, {
                  onSuccess: aoCongelar,
                  onSettled: () => setConfirmando(false),
                })
              }
            >
              {congelar.isPending ? "Congelando…" : "Confirmar congelamento"}
            </Botao>
          </div>
        </>
      ) : (
        <div className="flex justify-end">
          <Botao disabled={pendentes > 0} onClick={() => setConfirmando(true)}>
            Congelar banco
          </Botao>
        </div>
      )}
    </section>
  );
}
