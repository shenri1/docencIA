import type {
  Docente,
  Indice,
  MarcoBanco,
  MarcoSessao,
  Material,
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
