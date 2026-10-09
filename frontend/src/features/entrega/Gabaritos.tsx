import { useState } from "react";
import type { Gabarito, ItemGabarito, ProvasMontadas } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { letraDoItem } from "../../lib/aspectos";
import { ListaAspectos } from "../banco/ListaAspectos";
import { type Modalidade, useGabarito } from "./api";

type Versao = "A" | "B";
type FonteGabarito = ItemGabarito["fontes"][number];

/** uma prova e uma modalidade por vez; só o selecionado é pedido. */
export function Gabaritos({ provas }: { provas: ProvasMontadas }) {
  const [versao, setVersao] = useState<Versao>("A");
  const [modalidade, setModalidade] = useState<Modalidade>("simples");
  const provaId = versao === "A" ? provas.prova_a_id : provas.prova_b_id;
  const gabarito = useGabarito(provaId, modalidade);

  return (
    <section aria-labelledby="titulo-gabaritos" className="flex flex-col gap-4">
      <h2 id="titulo-gabaritos" className="font-serifa text-subtitulo">
        Gabaritos
      </h2>
      <div className="flex flex-wrap gap-4">
        <Seletor<Versao>
          rotulo="Prova"
          opcoes={[
            ["A", "Prova A"],
            ["B", "Prova B"],
          ]}
          valor={versao}
          aoMudar={setVersao}
        />
        <Seletor<Modalidade>
          rotulo="Modalidade"
          opcoes={[
            ["simples", "Simples"],
            ["comentado", "Comentado"],
          ]}
          valor={modalidade}
          aoMudar={setModalidade}
        />
      </div>
      {gabarito.isError && <Alerta variante="erro">{gabarito.error.message}</Alerta>}
      {gabarito.data ? (
        <ConteudoGabarito gabarito={gabarito.data} />
      ) : (
        !gabarito.isError && (
          <p className="font-grotesca text-detalhe text-texto-suave">Carregando o gabarito…</p>
        )
      )}
    </section>
  );
}

function Seletor<T extends string>({
  rotulo,
  opcoes,
  valor,
  aoMudar,
}: {
  rotulo: string;
  opcoes: [T, string][];
  valor: T;
  aoMudar: (valor: T) => void;
}) {
  return (
    <div role="group" aria-label={rotulo} className="flex gap-2">
      {opcoes.map(([opcao, texto]) => (
        <Botao
          key={opcao}
          variante={opcao === valor ? "primario" : "fantasma"}
          aria-pressed={opcao === valor}
          onClick={() => aoMudar(opcao)}
        >
          {texto}
        </Botao>
      ))}
    </div>
  );
}

function ConteudoGabarito({ gabarito }: { gabarito: Gabarito }) {
  const nome = `Gabarito ${gabarito.modalidade} da Prova ${gabarito.versao}`;
  return (
    <div role="region" aria-label={nome} className="flex flex-col gap-4">
      <p className="tabular font-grotesca text-detalhe text-texto-suave">
        {`${nome}, revisão r${gabarito.revisao_banco} do banco.`}
      </p>
      {gabarito.desatualizada && (
        <Alerta variante="aviso">
          O banco mudou desde a montagem das provas: este gabarito segue a prova como foi
          montada.
        </Alerta>
      )}
      {!gabarito.completo && (
        <Alerta
          variante="aviso"
          titulo="Gabarito incompleto: a exportação fica bloqueada até isto ser resolvido"
        >
          <ul>
            {gabarito.problemas.map((problema) => (
              <li key={problema}>{problema}</li>
            ))}
          </ul>
        </Alerta>
      )}
      {gabarito.modalidade === "simples" ? (
        <TabelaSimples gabarito={gabarito} />
      ) : (
        <ol className="flex flex-col gap-3">
          {gabarito.itens.map((item) => (
            <ItemComentado key={item.posicao} item={item} versao={gabarito.versao} />
          ))}
        </ol>
      )}
    </div>
  );
}

function TabelaSimples({ gabarito }: { gabarito: Gabarito }) {
  return (
    <table className="w-full border-collapse font-grotesca text-detalhe">
      <caption className="sr-only">{`Respostas da Prova ${gabarito.versao}`}</caption>
      <thead>
        <tr className="border-b border-borda text-left">
          <th scope="col" className="py-2 pr-4 font-semibold">Posição</th>
          <th scope="col" className="py-2 pr-4 font-semibold">Questão</th>
          <th scope="col" className="py-2 font-semibold">Resposta</th>
        </tr>
      </thead>
      <tbody>
        {gabarito.itens.map((item) => (
          <tr key={item.posicao} className="border-b border-borda align-top">
            <td className="tabular py-2 pr-4">{item.posicao}</td>
            <td className="tabular py-2 pr-4">Questão {item.numero} do banco</td>
            <td className="py-2">
              {item.letra ?? (
                <ul>
                  {item.aspectos.map((aspecto) => (
                    <li key={aspecto.ordem}>
                      {aspecto.item ? `${letraDoItem(aspecto.item)}) ` : ""}
                      {aspecto.texto}
                    </li>
                  ))}
                </ul>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ItemComentado({ item, versao }: { item: ItemGabarito; versao: string }) {
  return (
    <li>
      <article
        aria-label={`Gabarito da Prova ${versao}, posição ${item.posicao}`}
        className="cartao flex flex-col gap-3 p-4"
      >
        <header className="flex flex-wrap items-center gap-2 font-grotesca text-detalhe">
          <span className="tabular font-serifa text-subtitulo">{item.posicao}</span>
          <span className="tabular text-texto-suave">Questão {item.numero} do banco</span>
          {item.letra && <span className="chip">Correta: {item.letra}</span>}
        </header>

        {/* o texto sai como está; o aviso é como o docente sabe. */}
        {item.cita_letra && (
          <Alerta variante="aviso">
            O texto aprovado cita a letra de uma alternativa. Na prova as letras foram
            permutadas, então a letra citada pode não ser a mesma.
          </Alerta>
        )}

        {item.objetivo_cognitivo && (
          <p className="font-grotesca text-detalhe">
            <span className="font-semibold">Objetivo cognitivo: </span>
            {item.objetivo_cognitivo}
          </p>
        )}
        {item.justificativa_correta && (
          <div className="flex flex-col gap-1">
            <h3 className="font-grotesca text-detalhe font-semibold">Por que a correta é correta</h3>
            <p className="font-serifa">{item.justificativa_correta}</p>
          </div>
        )}

        {item.invalidacoes.length > 0 && (
          <div className="flex flex-col gap-1">
            <h3 className="font-grotesca text-detalhe font-semibold">
              Por que as outras estão erradas
            </h3>
            {item.invalidacoes_sem_letra && (
              <Alerta variante="aviso">
                O registro não diz qual motivo é de qual alternativa (banco anterior à 
                ou vínculo gravado inválido): os motivos aparecem sem letra.
              </Alerta>
            )}
            <ul className="flex flex-col gap-1 font-serifa">
              {item.invalidacoes.map((invalidacao, i) => (
                <li key={i}>
                  {invalidacao.letra
                    ? `${invalidacao.letra}) ${invalidacao.motivo}`
                    : invalidacao.motivo}
                </li>
              ))}
            </ul>
          </div>
        )}

        {item.aspectos.length > 0 && (
          <div className="flex flex-col gap-1">
            <h3 className="font-grotesca text-detalhe font-semibold">Aspectos esperados</h3>
            <ListaAspectos
              aspectos={item.aspectos}
              fonte={(aspecto) => <Fonte fonte={aspecto.fonte} />}
            />
          </div>
        )}

        {item.fontes.length > 0 && (
          <div className="flex flex-col gap-1">
            <h3 className="font-grotesca text-detalhe font-semibold">Fontes</h3>
            <ul className="flex flex-col gap-1">
              {item.fontes.map((fonte, i) => (
                <li key={i}>
                  <Fonte fonte={fonte} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </article>
    </li>
  );
}

function Fonte({ fonte }: { fonte: FonteGabarito }) {
  return (
    <p className="font-grotesca text-detalhe text-texto-suave">
      {fonte.trecho_base
        ? `${fonte.identificador_material}, ${fonte.localizacao}: “${fonte.trecho_base}”`
        : `${fonte.identificador_material}, ${fonte.localizacao}`}
    </p>
  );
}
