import type {
  Achado,
  Banco,
  Docente,
  Indice,
  MarcoBanco,
  MarcoSessao,
  Material,
  Orientacao,
  Questao,
  RelatorioImpacto,
  ResumoAuditoria,
  ResumoBanco,
  Sessao,
} from "../api/tipos";

export const DOCENTE: Docente = {
  id: 1,
  nome: "Ana Souza",
  credencial_institucional: "ana.souza",
  perfil: "docente",
};

export function umaSessao(sobrescrever: Partial<Sessao> = {}): Sessao {
  return {
    id: 1,
    disciplina: "Algoritmos",
    periodo: "2026.2",
    tema_escopo: "Ordenação",
    area_do_conhecimento: "Computação",
    k_alternativas: 5,
    p_f: 10,
    p_m: 60,
    p_d: 30,
    p_calculo: 0,
    estado: "rascunho",
    ...sobrescrever,
  };
}

export function umMarcoSessao(
  sobrescrever: Partial<MarcoSessao> = {},
): MarcoSessao {
  return {
    sessao_id: 1,
    marco: "m1_materiais",
    n_materiais: 0,
    comandos: ["prosseguir"],
    campos_prosseguir: [],
    bancos: [],
    ...sobrescrever,
  };
}

export function umMarcoBanco(sobrescrever: Partial<MarcoBanco> = {}): MarcoBanco {
  return {
    versao: "v1",
    banco_id: 1,
    revisao: 0,
    marco: "m3_exclusoes",
    motivo: null,
    n_alvo: 10,
    n_atual: 10,
    lacunas: 0,
    alerta_desvio: false,
    objetivas_ativas: 10,
    objetivas_auditadas: 0,
    comandos: ["prosseguir", "excluir", "auditar"],
    campos_prosseguir: ["versao", "revisao_esperada"],
    ...sobrescrever,
  };
}

export function umMaterial(sobrescrever: Partial<Material> = {}): Material {
  return {
    id: 1,
    identificador_curto: "S1",
    nome_arquivo: "aula-01.pptx",
    tipo: "slide",
    formato: "pptx",
    contagem_paginas_logicas: 24,
    origem_texto: "nativo",
    tamanho_bytes: 1_048_576,
    criado_em: "2026-10-01T12:00:00Z",
    ...sobrescrever,
  };
}

export function umIndice(
  materiais: Material[] = [],
  confirmado = false,
): Indice {
  return { materiais, confirmado };
}

export function umResumoBanco(sobrescrever: Partial<ResumoBanco> = {}): ResumoBanco {
  return {
    banco_id: 1,
    revisao: 0,
    geradas: 0,
    ja_existentes: 0,
    improdutivas: [],
    com_violacoes: [],
    geradas_por_tipo: { objetiva: 0, discursiva: 0 },
    ultimo_numero: null,
    restantes: 0,
    ...sobrescrever,
  };
}

export function umBanco(sobrescrever: Partial<Banco> = {}): Banco {
  return {
    banco_id: 1,
    versao: "v1",
    revisao: 0,
    rotulo: "v1.r0",
    estado: "aberto",
    n_alvo: 10,
    n_alvo_objetivas: 10,
    n_alvo_discursivas: 0,
    n_atual: 0,
    ultimo_relatorio: null,
    questoes: [],
    ...sobrescrever,
  };
}

export function umaQuestao(sobrescrever: Partial<Questao> = {}): Questao {
  return {
    numero: 1,
    tipo: "objetiva",
    estado: "ativa",
    faixa_dificuldade: "media",
    nivel_bloom: "entender",
    tema: "Ordenação",
    enunciado: "Qual é o papel do pivô no quicksort?",
    fontes: [
      {
        identificador_material: "S1",
        localizacao: "slide 4",
        trecho_base: "O quicksort escolhe um pivô e particiona o vetor em torno dele.",
      },
    ],
    violacoes: [],
    alternativas: [
      { letra: "A", texto: "Ordenar o vetor inteiro de uma vez" },
      { letra: "B", texto: "Particionar o vetor em menores e maiores" },
      { letra: "C", texto: "Mesclar duas metades ordenadas" },
    ],
    letra_correta: "B",
    formato: "proposicao",
    orientacoes_ids: [],
    aspectos_esperados: [],
    ...sobrescrever,
  };
}

export function umRelatorio(sobrescrever: Partial<RelatorioImpacto> = {}): RelatorioImpacto {
  return {
    revisao: 1,
    evento: "exclusao",
    n_final: 9,
    contagem_por_faixa: { objetiva: { facil: 1, media: 5, dificil: 3 } },
    desvio_observado: { objetiva: { facil: "1.1", media: "-4.4", dificil: "3.3" } },
    alerta_desvio: false,
    timestamp: "2026-10-01T12:00:00Z",
    ...sobrescrever,
  };
}

export function umResumoAuditoria(
  sobrescrever: Partial<ResumoAuditoria> = {},
): ResumoAuditoria {
  return {
    banco_id: 1,
    revisao_auditada: 0,
    auditadas: 0,
    ja_auditadas: 0,
    discursivas_ignoradas: 0,
    questoes: [],
    proporcao_com_achado: "0.00",
    sem_verificacao_de_forma: 0,
    ...sobrescrever,
  };
}

export function umAchado(sobrescrever: Partial<Achado> = {}): Achado {
  return {
    risco: "distrator_indefensavel",
    alvo: "C",
    localizacao: "slide 4",
    trecho_fonte: "O quicksort escolhe um pivô e particiona o vetor em torno dele.",
    proposta_ajuste: "Reescreva a alternativa C com uma ideia que o aluno não elimine de imediato.",
    ...sobrescrever,
  };
}

export function umaOrientacao(sobrescrever: Partial<Orientacao> = {}): Orientacao {
  return {
    id: 1,
    origem: "sessao",
    estado: "ativa",
    o_que_mudar: "Prefiro exemplos práticos",
    cruzar_com: null,
    banco_id: null,
    numero_origem: null,
    criada_em: "2026-10-13T12:00:00Z",
    ...sobrescrever,
  };
}
