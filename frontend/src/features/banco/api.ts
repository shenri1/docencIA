import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useApi } from "../../app/api-context";
import { desembrulhar } from "../../api/cliente";
import { ErroApi } from "../../api/erros";
import type { ResumoBanco } from "../../api/tipos";
import { chaves } from "../sessoes/api";

export interface ParametrosGeracao {
  versao: string;
  n_objetivas: number;
  n_discursivas: number;
}

export interface Acumulado {
  geradas: number;
  improdutivas: ResumoBanco["improdutivas"];
  comViolacoes: ResumoBanco["com_violacoes"];
  ultimoNumero: number | null;
  total: number;
}

type Estado = "parado" | "gerando" | "pausando";

function comoErroApi(erro: unknown): ErroApi {
  return erro instanceof ErroApi ? erro : new ErroApi(0, String(erro));
}

/**
 * uma questão por chamada, em laço, até `restantes == 0`. Cada
 * chamada dura o tempo de uma questão — nenhuma passa do timeout do navegador
 * ou do proxy —, e cada questão é gravada sozinha: parar no meio não perde nada.
 */
export function useGeracaoEmLotes(sessaoId: number) {
  const cliente = useApi();
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState<Estado>("parado");
  const [acumulado, setAcumulado] = useState<Acumulado | null>(null);
  const [erro, setErro] = useState<ErroApi | null>(null);
  const pausaPedida = useRef(false);

  async function iniciar(params: ParametrosGeracao) {
    pausaPedida.current = false;
    setErro(null);
    setEstado("gerando");
    let atual: Acumulado = {
      geradas: 0,
      improdutivas: [],
      comViolacoes: [],
      ultimoNumero: null,
      total: params.n_objetivas + params.n_discursivas,
    };
    setAcumulado(atual);
    let apos = 0;
    try {
      for (;;) {
        const resposta = await desembrulhar(
          cliente.POST("/sessoes/{sessao_id}/banco", {
            params: { path: { sessao_id: sessaoId } },
            body: { ...params, apos, limite: 1 },
          }),
        );
        atual = {
          ...atual,
          geradas: atual.geradas + resposta.geradas,
          improdutivas: [...atual.improdutivas, ...resposta.improdutivas],
          comViolacoes: [...atual.comViolacoes, ...resposta.com_violacoes],
          ultimoNumero: resposta.ultimo_numero ?? atual.ultimoNumero,
        };
        setAcumulado(atual);
        // `ultimo_numero` nulo: nada a tentar — sem isto um banco completo giraria
        // para sempre.
        if (resposta.ultimo_numero === null || resposta.restantes === 0) break;
        if (pausaPedida.current) break;
        apos = resposta.ultimo_numero;
      }
    } catch (e) {
      setErro(comoErroApi(e));
    } finally {
      setEstado("parado");
      // O marco é quem diz se ficaram lacunas.
      await queryClient.invalidateQueries({ queryKey: chaves.marco(sessaoId) });
    }
  }

  /** A retomada exige as contagens por tipo da criação; o marco só traz n_alvo. */
  async function continuar(bancoId: number) {
    setErro(null);
    try {
      const banco = await desembrulhar(
        cliente.GET("/bancos/{banco_id}", {
          params: { path: { banco_id: bancoId }, query: { de: 1, ate: 1 } },
        }),
      );
      await iniciar({
        versao: banco.versao,
        n_objetivas: banco.n_alvo_objetivas,
        n_discursivas: banco.n_alvo_discursivas,
      });
    } catch (e) {
      setErro(comoErroApi(e));
    }
  }

  function pausar() {
    pausaPedida.current = true;
    setEstado("pausando");
  }

  return { estado, acumulado, erro, iniciar, continuar, pausar };
}
