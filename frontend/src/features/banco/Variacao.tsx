import { useIsMutating } from "@tanstack/react-query";
import type { Banco, Questao } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
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
  const insuficiencia = pedir.data?.motivo_insuficiencia ? pedir.data : null;

  return (
    <div className="flex flex-col items-end gap-2">
      <Botao variante="fantasma" disabled={ocupado} onClick={() => pedir.mutate(numero)}>
        {pedir.isPending ? "Gerando variação…" : "Pedir variação"}
      </Botao>
      {insuficiencia && (
        <Alerta variante="aviso" titulo="O material não sustentou outra questão">
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
}: {
  banco: Banco;
  sessaoId: number;
  original: Questao;
  candidata: Questao;
  aoConcluir: (texto: string) => void;
}) {
  const aceitar = useAceitarVariacao(banco.banco_id, sessaoId);
  const rejeitar = useRejeitarVariacao(banco.banco_id, sessaoId);
  const erro = aceitar.error ?? rejeitar.error;
  const ocupado = aceitar.isPending || rejeitar.isPending;

  return (
    <section aria-label={`Variação da questão ${original.numero}`} className="flex flex-col gap-3">
      <div className="grid gap-4 md:grid-cols-2">
        <CartaoQuestao questao={original} />
        <CartaoQuestao questao={candidata} />
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
