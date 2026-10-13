import { useIsMutating } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import type { Banco, DirecaoVariacao, Orientacao, Questao } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { CartaoQuestao } from "./CartaoQuestao";
import {
  chavesBanco,
  mensagemDeErro,
  useAceitarVariacao,
  usePedirVariacao,
  useRejeitarVariacao,
} from "./curadoria";

export function PedirVariacao({
  bancoId,
  sessaoId,
  numero,
}: {
  bancoId: number;
  sessaoId: number;
  numero: number;
}) {
  const pedir = usePedirVariacao(bancoId, sessaoId);
  // Um pedido por vez na mesa inteira: cada um ocupa a GPU por ~38 s.
  const ocupado = useIsMutating({ mutationKey: chavesBanco.proposta(bancoId) }) > 0;
  const [aberto, setAberto] = useState(false);
  const [cruzar, setCruzar] = useState("");
  const [mudar, setMudar] = useState("");
  const [acumular, setAcumular] = useState(false);
  const guiada = cruzar.trim() !== "" || mudar.trim() !== "";
  const insuficiencia = pedir.data?.motivo_insuficiencia ? pedir.data : null;
  const assunto = pedir.variables?.direcao?.cruzar_com ?? null;

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    // Sem texto, o pedido vai sem corpo: é a substituição de sempre.
    const direcao: DirecaoVariacao | undefined = guiada
      ? { cruzar_com: cruzar.trim() || null, o_que_mudar: mudar.trim() || null, acumular }
      : undefined;
    pedir.mutate({ numero, direcao });
    setAberto(false);
  }

  return (
    <div className="flex flex-col items-end gap-2">
      {aberto ? (
        <form
          noValidate
          onSubmit={enviar}
          aria-label={`Pedir variação da questão ${numero}`}
          className="flex w-full flex-col gap-3"
        >
          <Campo
            rotulo="Articular com (um assunto do seu material)"
            value={cruzar}
            maxLength={200}
            onChange={(e) => setCruzar(e.target.value)}
          />
          <Campo
            rotulo="O que mudar"
            value={mudar}
            maxLength={500}
            onChange={(e) => setMudar(e.target.value)}
          />
          <label className="flex items-center gap-2 font-grotesca text-detalhe">
            <input
              type="checkbox"
              checked={acumular}
              disabled={!guiada}
              onChange={(e) => setAcumular(e.target.checked)}
            />
            Aplicar também às próximas gerações desta sessão
          </label>
          <div className="flex justify-end gap-3">
            <Botao variante="fantasma" onClick={() => setAberto(false)}>
              Cancelar
            </Botao>
            <Botao type="submit" disabled={ocupado}>
              {guiada ? "Gerar variação" : "Gerar outra questão"}
            </Botao>
          </div>
        </form>
      ) : (
        <Botao variante="fantasma" disabled={ocupado} onClick={() => setAberto(true)}>
          {pedir.isPending ? "Gerando variação…" : "Pedir variação"}
        </Botao>
      )}
      {insuficiencia && (
        <Alerta
          variante="aviso"
          titulo={
            assunto
              ? `O material não sustentou a relação com ${assunto}`
              : "O material não sustentou outra questão"
          }
        >
          {insuficiencia.motivo_insuficiencia}
          {insuficiencia.localizacao && ` (${insuficiencia.localizacao})`}. A questão original
          continua no banco.
        </Alerta>
      )}
      {pedir.error && <Alerta variante="erro">{mensagemDeErro(pedir.error)}</Alerta>}
    </div>
  );
}

export function Comparacao({
  banco,
  sessaoId,
  original,
  candidata,
  aoConcluir,
  orientacoesDe,
}: {
  banco: Banco;
  sessaoId: number;
  original: Questao;
  candidata: Questao;
  aoConcluir: (texto: string) => void;
  orientacoesDe: (questao: Questao) => Orientacao[];
}) {
  const aceitar = useAceitarVariacao(banco.banco_id, sessaoId);
  const rejeitar = useRejeitarVariacao(banco.banco_id, sessaoId);
  const erro = aceitar.error ?? rejeitar.error;
  const ocupado = aceitar.isPending || rejeitar.isPending;

  return (
    <section aria-label={`Variação da questão ${original.numero}`} className="flex flex-col gap-3">
      <div className="grid gap-4 md:grid-cols-2">
        <CartaoQuestao questao={original} orientacoes={orientacoesDe(original)} />
        <CartaoQuestao questao={candidata} orientacoes={orientacoesDe(candidata)} />
      </div>
      {erro && <Alerta variante="erro">{mensagemDeErro(erro)}</Alerta>}
      <div className="flex justify-end gap-3">
        <Botao
          variante="fantasma"
          disabled={ocupado}
          onClick={() =>
            rejeitar.mutate(original.numero, {
              onSuccess: () =>
                aoConcluir("Variação rejeitada. A questão original continua no banco."),
            })
          }
        >
          Rejeitar variação
        </Botao>
        <Botao
          variante="manter"
          disabled={ocupado}
          onClick={() =>
            aceitar.mutate(
              { numero: original.numero, revisao_esperada: banco.revisao },
              {
                onSuccess: (relatorio) =>
                  aoConcluir(
                    `Variação aceita. O banco está na revisão r${relatorio.revisao}, com ${relatorio.n_final} questões ativas.`,
                  ),
              },
            )
          }
        >
          Aceitar variação
        </Botao>
      </div>
    </section>
  );
}
