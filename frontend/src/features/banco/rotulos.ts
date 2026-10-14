import type { Questao } from "../../api/tipos";

export const ROTULO_TIPO_QUESTAO: Record<Questao["tipo"], string> = {
  objetiva: "Objetiva",
  discursiva: "Discursiva",
};

export const ROTULO_FAIXA: Record<Questao["faixa_dificuldade"], string> = {
  facil: "Fácil",
  media: "Média",
  dificil: "Difícil",
};

// o enum diz `entender`; o diz "Compreender".
export const ROTULO_BLOOM: Record<Questao["nivel_bloom"], string> = {
  lembrar: "Lembrar",
  entender: "Compreender",
  aplicar: "Aplicar",
  analisar: "Analisar",
  avaliar: "Avaliar",
  criar: "Criar",
};

// Só os formatos montados ganham rótulo: proposição é o padrão.
export const ROTULO_FORMATO: Record<Questao["formato"], string | null> = {
  proposicao: null,
  afirmativas: "Afirmativas",
  assercao_razao: "Asserção-razão",
  calculo: "Cálculo",
};
