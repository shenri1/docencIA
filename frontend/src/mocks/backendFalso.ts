/**
 * Back-end falso com estado, só para o front avançar sem API nem Ollama
 * e para os testes de fluxo. Reproduz o contrato e os erros de domínio das telas já feitas
 * (auth, sessões, materiais, índice, geração e curadoria); não reproduz regra de negócio além do
 * necessário para exercitar a interface. A montagem de provas do falso é
 * simplificada: A recebe as primeiras questões ativas de cada tipo, B as seguintes,
 * e B completa com as de A quando faltam (compartilhadas); não há subtema nem plano de letras.
 *
 * Gatilhos de teste manual: um arquivo cujo nome começa com "ilegivel" é recusado
 * como PDF sem texto extraível; extensão fora de PDF/PPTX/DOCX/TXT dá 415;
 * versão de banco começando com "lacuna" deixa o número 2 sem sustentação na
 * primeira tentativa; versão começando com "insuf" faz todo pedido de variação
 * voltar com insuficiência de fonte; versão começando com "achados" faz a
 * auditoria apontar problemas nas questões 1 (correta não única) e 2 (assimetria
 * de forma); cadastrar a credencial "admin" cria um administrador (na
 * API real, ele vem da migração e1a4c8f02b77). O estado nasce com o prompt mestre
 * 1.0.0 ativo, como depois da migração.
 */
import { delay, http, HttpResponse } from "msw";
import type {
  Achado,
  Banco,
  Docente,
  MarcoBanco,
  MarcoSessao,
  Material,
  Prova,
  Prompt,
  PromptCriar,
  PropostaSubstituicao,
  ProvasMontadas,
  Questao,
  RelatorioImpacto,
  ResumoAuditoria,
  ResumoBanco,
  Sessao,
} from "../api/tipos";

interface DocenteFalso extends Docente {
  senha: string;
}

export interface BancoFalso {
  banco_id: number;
  versao: string;
  n_objetivas: number;
  n_discursivas: number;
  gerados: Set<number>;
  recusados: Set<number>;
  revisao: number;
  estado: Banco["estado"];
  /** Todas as linhas, como na tabela: ativas, excluídas, substituídas, candidatas. */
  questoes: Questao[];
  ultimo_relatorio: RelatorioImpacto | null;
  auditoria?: AuditoriaFalsa;
  /** Provas montadas: as questões de cada uma, em ordem de posição. */
  provas?: ProvasFalsas;
}

export interface AuditoriaFalsa {
  /** número → achados que a auditoria encontra nele (padrão: nenhum). */
  achados: Record<number, Achado[]>;
  /** número → revisão do banco em que foi auditado. */
  feitas: Map<number, number>;
  /** Quantas vezes o POST foi chamado. */
  chamadas: number;
  /** `limite` de cada chamada, na ordem. */
  limites: Array<number | null>;
  /** A chamada de número N (a partir de 1) responde 502, sem auditar nada. */
  falhaNa?: number;
  /** Atraso de cada POST, em ms, para os testes conseguirem pausar. */
  atraso?: number;
}

export interface ProvasFalsas {
  a: Questao[];
  b: Questao[];
  /** Revisão do banco na montagem. */
  revisao: number;
  /** O falso não tem subtema: o teste diz quantas questões ficariam sem. */
  sem_subtema: number;
}

export function auditoriaFalsa(parcial: Partial<AuditoriaFalsa> = {}): AuditoriaFalsa {
  return { achados: {}, feitas: new Map(), chamadas: 0, limites: [], ...parcial };
}

interface SessaoFalsa extends Sessao {
  materiais: Material[];
  banco?: BancoFalso;
}

export interface EstadoFalso {
  docentes: DocenteFalso[];
  sessoes: SessaoFalsa[];
  proximoMaterial: number;
  prompts: Prompt[];
}

function promptInicial(): Prompt {
  return {
    id: 1,
    versao: "1.0.0",
    papel_definido: "docente universitário elaborador de questões",
    conteudo: "Você é um docente universitário elaborador de questões…",
    hash_modulos: "0".repeat(64),
    ativo: true,
    criado_em: new Date().toISOString(),
  };
}

export function novoEstado(): EstadoFalso {
  return { docentes: [], sessoes: [], proximoMaterial: 1, prompts: [promptInicial()] };
}

const PREFIXO: Record<Material["tipo"], string> = { slide: "S", pdf: "P", livro: "L" };
const FORMATOS = ["pdf", "pptx", "docx", "txt"] as const;
const FAIXAS = ["facil", "media", "dificil"] as const;

export function questaoFalsa(numero: number, tipo: Questao["tipo"] = "objetiva"): Questao {
  const fonte = {
    identificador_material: "S1",
    localizacao: `slide ${numero}`,
    trecho_base: `Trecho do material que sustenta a questão ${numero}.`,
  };
  return {
    numero,
    tipo,
    estado: "ativa",
    faixa_dificuldade: FAIXAS[numero % 3] ?? "media",
    nivel_bloom: "entender",
    tema: "Ordenação",
    enunciado: `Enunciado da questão ${numero}.`,
    fontes: [fonte],
    violacoes: [],
    alternativas:
      tipo === "objetiva"
        ? ["A", "B", "C", "D", "E"].map((letra) => ({
            letra,
            texto: `Alternativa ${letra} da questão ${numero}`,
          }))
        : [],
    letra_correta: tipo === "objetiva" ? "B" : null,
    aspectos_esperados:
      tipo === "discursiva"
        ? [{ ordem: 1, texto: `Aspecto esperado da questão ${numero}`, fonte }]
        : [],
  };
}

const ativasDe = (banco: BancoFalso) => banco.questoes.filter((q) => q.estado === "ativa");

/** Seleção do falso: A pega as primeiras de cada tipo, B as seguintes, e B
 * completa com as de A quando faltam — essas são as compartilhadas. */
export function montarFalso(
  banco: BancoFalso,
  nObjetivas: number,
  nDiscursivas: number,
): ProvasFalsas {
  const escolher = (tipo: Questao["tipo"], n: number) => {
    const doTipo = ativasDe(banco).filter((q) => q.tipo === tipo);
    const a = doTipo.slice(0, n);
    const resto = doTipo.slice(n, 2 * n);
    return { a, b: [...resto, ...a.slice(0, n - resto.length)] };
  };
  const objetivas = escolher("objetiva", nObjetivas);
  const discursivas = escolher("discursiva", nDiscursivas);
  banco.provas = {
    a: [...objetivas.a, ...discursivas.a],
    b: [...objetivas.b, ...discursivas.b],
    revisao: banco.revisao,
    sem_subtema: 0,
  };
  return banco.provas;
}

const idDaProva = (banco: BancoFalso, versao: "A" | "B") =>
  banco.banco_id * 10 + (versao === "A" ? 1 : 2);

const objetivasEm = (questoes: Questao[]) =>
  questoes.filter((q) => q.tipo === "objetiva").length;

function montadasFalsas(banco: BancoFalso, provas: ProvasFalsas): ProvasMontadas {
  const numerosB = new Set(provas.b.map((q) => q.numero));
  const compartilhadas = provas.a
    .map((q) => q.numero)
    .filter((n) => numerosB.has(n))
    .sort((x, y) => x - y);
  return {
    prova_a_id: idDaProva(banco, "A"),
    prova_b_id: idDaProva(banco, "B"),
    revisao_banco: provas.revisao,
    compartilhadas,
    sem_subtema: provas.sem_subtema,
    verificacao: {
      violacoes: [],
      colisoes_letras: 0,
      posicoes_objetivas: Math.min(objetivasEm(provas.a), objetivasEm(provas.b)),
      compartilhadas: compartilhadas.length,
      subtemas_compartilhados: {},
    },
  };
}

function provaLida(banco: BancoFalso, provas: ProvasFalsas, versao: "A" | "B"): Prova {
  const questoes = versao === "A" ? provas.a : provas.b;
  const objetivas = objetivasEm(questoes);
  return {
    prova_id: idDaProva(banco, versao),
    versao,
    estado: "montada",
    n_questoes: questoes.length,
    n_objetivas: objetivas,
    n_discursivas: questoes.length - objetivas,
    revisao_banco: provas.revisao,
    banco_revisao_atual: banco.revisao,
    desatualizada: provas.revisao !== banco.revisao,
    // só letra e texto, nunca a correta.
    itens: questoes.map((q, i) => ({
      posicao: i + 1,
      numero: q.numero,
      tipo: q.tipo,
      faixa_dificuldade: q.faixa_dificuldade,
      enunciado: q.enunciado,
      alternativas: q.alternativas.map(({ letra, texto }) => ({ letra, texto })),
    })),
  };
}

const ACHADOS_PADRAO: Record<number, Achado[]> = {
  1: [
    {
      risco: "correta_nao_unica",
      alvo: "C",
      localizacao: "slide 1",
      trecho_fonte: "Trecho do material que também sustenta a alternativa C.",
      proposta_ajuste: "Torne a alternativa C claramente incorreta ou reformule o enunciado.",
    },
  ],
  2: [
    {
      risco: "assimetria_forma",
      alvo: "A",
      localizacao: null,
      trecho_fonte: null,
      proposta_ajuste: "A alternativa A é bem mais longa que as outras — encurte-a.",
    },
  ],
};

const objetivasAtivas = (banco: BancoFalso) =>
  ativasDe(banco).filter((q) => q.tipo === "objetiva");
const auditadasDe = (banco: BancoFalso) =>
  objetivasAtivas(banco).filter((q) => banco.auditoria?.feitas.get(q.numero) === banco.revisao);

function achadosDe(banco: BancoFalso, numero: number): Achado[] {
  const roteiro = banco.auditoria?.achados[numero];
  if (roteiro) return roteiro;
  return banco.versao.startsWith("achados") ? (ACHADOS_PADRAO[numero] ?? []) : [];
}

function resumoDaAuditoria(banco: BancoFalso, jaAntes: number | null): ResumoAuditoria {
  const feitas = auditadasDe(banco);
  const questoes = feitas
    .map((q) => ({ numero: q.numero, achados: achadosDe(banco, q.numero) }))
    .filter((q) => q.achados.length > 0);
  return {
    banco_id: banco.banco_id,
    revisao_auditada: banco.revisao,
    auditadas: feitas.length,
    ja_auditadas: jaAntes ?? feitas.length,
    discursivas_ignoradas: ativasDe(banco).filter((q) => q.tipo === "discursiva").length,
    questoes,
    proporcao_com_achado:
      feitas.length === 0 ? "0.00" : ((100 * questoes.length) / feitas.length).toFixed(2),
  };
}

function relatorioFalso(banco: BancoFalso, evento: RelatorioImpacto["evento"]): RelatorioImpacto {
  const ativas = ativasDe(banco);
  const contagem: RelatorioImpacto["contagem_por_faixa"] = {};
  for (const q of ativas) {
    const doTipo = (contagem[q.tipo] ??= { facil: 0, media: 0, dificil: 0 });
    doTipo[q.faixa_dificuldade] = (doTipo[q.faixa_dificuldade] ?? 0) + 1;
  }
  return {
    revisao: banco.revisao,
    evento,
    n_final: ativas.length,
    contagem_por_faixa: contagem,
    desvio_observado: {},
    alerta_desvio: false,
    timestamp: new Date().toISOString(),
  };
}

const erro = (status: number, detail: string, codigo: string, extras = {}) =>
  HttpResponse.json({ detail, codigo, ...extras }, { status });

function marcoDoBanco(banco: BancoFalso): MarcoBanco {
  const n_alvo = banco.n_objetivas + banco.n_discursivas;
  const ativas = ativasDe(banco);
  return {
    versao: banco.versao,
    banco_id: banco.banco_id,
    revisao: banco.revisao,
    marco: banco.provas
      ? "m10_docx"
      : banco.estado === "congelado"
        ? "m6_provas"
        : "m3_exclusoes",
    motivo: null,
    n_alvo,
    n_atual: ativas.length,
    lacunas: n_alvo - banco.gerados.size,
    alerta_desvio: false,
    objetivas_ativas: objetivasAtivas(banco).length,
    objetivas_auditadas: auditadasDe(banco).length,
    comandos: ["prosseguir", "excluir", "auditar"],
    campos_prosseguir: ["versao", "revisao_esperada"],
  };
}

export function criarHandlers(base: string, estado: EstadoFalso = novoEstado()) {
  const docenteDoToken = (request: Request) => {
    const token = request.headers.get("authorization")?.replace("Bearer ", "");
    const id = Number(token?.replace("mock-token-", ""));
    return estado.docentes.find((d) => d.id === id);
  };
  const naoAutorizado = () =>
    erro(401, "Token inválido ou expirado.", "TOKEN_INVALIDO");
  const proibido = () =>
    erro(403, "Perfil insuficiente para este recurso.", "PERFIL_INSUFICIENTE");
  const publico = ({ senha: _senha, ...docente }: DocenteFalso): Docente => docente;

  const sessaoDe = (id: string | readonly string[] | undefined) =>
    estado.sessoes.find((s) => s.id === Number(id));
  const bancoDe = (id: string | readonly string[] | undefined) =>
    estado.sessoes.find((s) => s.banco?.banco_id === Number(id))?.banco;
  const bancoNaoEncontrado = (id: unknown) =>
    erro(404, `Banco ${String(id)} não encontrado.`, "BANCO_NAO_ENCONTRADO");
  const revisaoDesatualizada = (banco: BancoFalso, esperada: number) =>
    esperada === banco.revisao
      ? null
      : erro(
          409,
          `O banco está na revisão ${banco.revisao} e o comando esperava a ${esperada}. Leia o banco de novo antes de decidir.`,
          "REVISAO_DESATUALIZADA",
        );
  /** Toda mudança do banco ganha revisão nova e relatório de impacto. */
  const registrar = (banco: BancoFalso, evento: RelatorioImpacto["evento"]) => {
    banco.revisao += 1;
    banco.ultimo_relatorio = relatorioFalso(banco, evento);
    return HttpResponse.json(banco.ultimo_relatorio);
  };

  return [
    http.post(`${base}/auth/registrar`, async ({ request }) => {
      const dados = (await request.json()) as {
        nome: string;
        credencial_institucional: string;
        senha: string;
      };
      if (estado.docentes.some((d) => d.credencial_institucional === dados.credencial_institucional)) {
        return erro(
          409,
          `Credencial institucional '${dados.credencial_institucional}' já cadastrada.`,
          "CREDENCIAL_JA_CADASTRADA",
        );
      }
      const docente: DocenteFalso = {
        id: estado.docentes.length + 1,
        nome: dados.nome,
        credencial_institucional: dados.credencial_institucional,
        perfil: dados.credencial_institucional === "admin" ? "administrador" : "docente",
        senha: dados.senha,
      };
      estado.docentes.push(docente);
      return HttpResponse.json(publico(docente), { status: 201 });
    }),

    http.post(`${base}/auth/login`, async ({ request }) => {
      const form = new URLSearchParams(await request.text());
      const docente = estado.docentes.find(
        (d) =>
          d.credencial_institucional === form.get("username") &&
          d.senha === form.get("password"),
      );
      if (!docente) {
        return erro(401, "Credenciais inválidas.", "CREDENCIAIS_INVALIDAS");
      }
      return HttpResponse.json({
        access_token: `mock-token-${docente.id}`,
        token_type: "bearer",
      });
    }),

    http.get(`${base}/auth/me`, ({ request }) => {
      const docente = docenteDoToken(request);
      return docente ? HttpResponse.json(publico(docente)) : naoAutorizado();
    }),

    http.get(`${base}/sessoes`, ({ request }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const url = new URL(request.url);
      const limit = Number(url.searchParams.get("limit") ?? 20);
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return HttpResponse.json(
        estado.sessoes.slice(offset, offset + limit).map(({ materiais: _m, banco: _b, ...s }) => s),
      );
    }),

    http.post(`${base}/sessoes`, async ({ request }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const dados = (await request.json()) as Omit<Sessao, "id" | "estado">;
      const soma = dados.p_f + dados.p_m + dados.p_d;
      if (soma !== 100) {
        return erro(
          422,
          `pF + pM + pD deve somar exatamente 100%. Recebido pF=${dados.p_f}, pM=${dados.p_m}, pD=${dados.p_d} — soma ${soma}.`,
          "PARAMETROS_INCONSISTENTES",
          { soma },
        );
      }
      const sessao: SessaoFalsa = {
        ...dados,
        id: estado.sessoes.length + 1,
        estado: "rascunho",
        materiais: [],
      };
      estado.sessoes.push(sessao);
      const { materiais: _m, banco: _b, ...resposta } = sessao;
      return HttpResponse.json(resposta, { status: 201 });
    }),

    http.get(`${base}/sessoes/:id`, ({ request, params }) => {
      const sessao = sessaoDe(params.id);
      if (!docenteDoToken(request)) return naoAutorizado();
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      const { materiais: _m, banco: _b, ...resposta } = sessao;
      return HttpResponse.json(resposta);
    }),

    http.get(`${base}/sessoes/:id/marco`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const sessao = sessaoDe(params.id);
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      const rascunho = sessao.estado === "rascunho";
      const marco: MarcoSessao = {
        sessao_id: sessao.id,
        marco: rascunho ? "m1_materiais" : "m2_banco",
        n_materiais: sessao.materiais.length,
        comandos: ["prosseguir"],
        campos_prosseguir: rascunho ? [] : ["versao", "n_objetivas", "n_discursivas"],
        bancos: sessao.banco ? [marcoDoBanco(sessao.banco)] : [],
      };
      return HttpResponse.json(marco);
    }),

    http.post(`${base}/sessoes/:id/materiais`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const sessao = sessaoDe(params.id);
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      if (sessao.estado !== "rascunho") {
        return erro(
          409,
          "Operação não permitida no estado atual da sessão: o índice de materiais já foi confirmado e está congelado.",
          "SESSAO_ESTADO_INVALIDO",
        );
      }
      const form = await request.formData();
      const arquivo = form.get("arquivo") as File;
      const tipo = form.get("tipo") as Material["tipo"];
      const extensao = arquivo.name.split(".").pop()?.toLowerCase() ?? "";
      if (!(FORMATOS as readonly string[]).includes(extensao)) {
        return erro(
          415,
          `Formato não suportado: ${extensao}. Aceitos: PDF, PPTX, DOCX, TXT.`,
          "FORMATO_NAO_SUPORTADO",
          { detectado: extensao },
        );
      }
      if (arquivo.name.startsWith("ilegivel")) {
        return erro(
          422,
          "Não foi possível extrair texto confiável deste PDF, nem com OCR. Envie uma versão com texto selecionável.",
          "PDF_OCR_INSUFICIENTE",
          { motivo: "pouco texto reconhecido", paginas_afetadas: [1, 2] },
        );
      }
      const repetido = sessao.materiais.find((m) => m.nome_arquivo === arquivo.name);
      if (repetido) {
        return erro(
          409,
          `Este arquivo já foi enviado nesta sessão como ${repetido.identificador_curto}.`,
          "MATERIAL_DUPLICADO",
          { identificador_curto: repetido.identificador_curto },
        );
      }
      const doMesmoTipo = sessao.materiais.filter((m) => m.tipo === tipo).length;
      const material: Material = {
        id: estado.proximoMaterial++,
        identificador_curto: `${PREFIXO[tipo]}${doMesmoTipo + 1}`,
        nome_arquivo: arquivo.name,
        tipo,
        formato: extensao as Material["formato"],
        contagem_paginas_logicas: extensao === "txt" ? null : 12,
        origem_texto: "nativo",
        tamanho_bytes: arquivo.size,
        criado_em: new Date().toISOString(),
      };
      sessao.materiais.push(material);
      return HttpResponse.json(material, { status: 201 });
    }),

    http.get(`${base}/sessoes/:id/materiais/indice`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const sessao = sessaoDe(params.id);
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      return HttpResponse.json({
        materiais: sessao.materiais,
        confirmado: sessao.estado !== "rascunho",
      });
    }),

    http.delete(`${base}/sessoes/:id/materiais/:materialId`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const sessao = sessaoDe(params.id);
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      if (sessao.estado !== "rascunho") {
        return erro(
          409,
          "Operação não permitida no estado atual da sessão: o índice de materiais já foi confirmado e está congelado.",
          "SESSAO_ESTADO_INVALIDO",
        );
      }
      sessao.materiais = sessao.materiais.filter((m) => m.id !== Number(params.materialId));
      return new HttpResponse(null, { status: 204 });
    }),

    http.post(`${base}/sessoes/:id/materiais/confirmar`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const sessao = sessaoDe(params.id);
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      if (sessao.materiais.length === 0) {
        return erro(
          409,
          "A sessão não tem nenhum material enviado — envie ao menos um antes de confirmar o índice.",
          "INDICE_VAZIO",
        );
      }
      sessao.estado = "materiais_confirmados";
      return HttpResponse.json({ materiais: sessao.materiais, confirmado: true });
    }),

    http.post(`${base}/sessoes/:id/banco`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const sessao = sessaoDe(params.id);
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      const dados = (await request.json()) as {
        versao: string;
        n_objetivas: number;
        n_discursivas: number;
        apos?: number;
        limite?: number | null;
      };
      sessao.banco ??= {
        banco_id: sessao.id,
        versao: dados.versao,
        n_objetivas: dados.n_objetivas,
        n_discursivas: dados.n_discursivas,
        gerados: new Set(),
        recusados: new Set(),
        revisao: 0,
        estado: "aberto",
        questoes: [],
        ultimo_relatorio: null,
      };
      const banco = sessao.banco;
      const numeros = Array.from(
        { length: banco.n_objetivas + banco.n_discursivas },
        (_, i) => i + 1,
      );
      const pendentes = numeros.filter((n) => n > (dados.apos ?? 0) && !banco.gerados.has(n));
      const tentar = dados.limite ? pendentes.slice(0, dados.limite) : pendentes;
      const improdutivas: ResumoBanco["improdutivas"] = [];
      for (const n of tentar) {
        if (banco.versao.startsWith("lacuna") && n === 2 && !banco.recusados.has(n)) {
          banco.recusados.add(n);
          improdutivas.push({ numero: n, localizacao: "página 2", motivo: "o trecho não sustenta a questão" });
        } else {
          banco.gerados.add(n);
          banco.questoes.push(
            questaoFalsa(n, n > banco.n_objetivas ? "discursiva" : "objetiva"),
          );
        }
      }
      const resumo: ResumoBanco = {
        banco_id: banco.banco_id,
        revisao: 0,
        geradas: tentar.length - improdutivas.length,
        ja_existentes: 0,
        improdutivas,
        com_violacoes: [],
        geradas_por_tipo: { objetiva: tentar.length - improdutivas.length, discursiva: 0 },
        ultimo_numero: tentar.at(-1) ?? null,
        restantes: pendentes.length - tentar.length,
      };
      return HttpResponse.json(resumo, { status: 201 });
    }),

    // O falso sempre devolve o gabarito: a mesa sempre pede com_gabarito=true.
    http.get(`${base}/bancos/:id`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const url = new URL(request.url);
      const de = Number(url.searchParams.get("de") ?? 1);
      const ate = Number(url.searchParams.get("ate") ?? 20);
      const historico = url.searchParams.get("incluir_historico") === "true";
      const resposta: Banco = {
        banco_id: banco.banco_id,
        versao: banco.versao,
        revisao: banco.revisao,
        rotulo: `${banco.versao}.r${banco.revisao}`,
        estado: banco.estado,
        n_alvo: banco.n_objetivas + banco.n_discursivas,
        n_alvo_objetivas: banco.n_objetivas,
        n_alvo_discursivas: banco.n_discursivas,
        n_atual: ativasDe(banco).length,
        ultimo_relatorio: banco.ultimo_relatorio,
        questoes: banco.questoes
          .filter(
            (q) =>
              q.numero >= de && q.numero <= ate && (historico || q.estado === "ativa"),
          )
          .sort((a, b) => a.numero - b.numero),
      };
      return HttpResponse.json(resposta);
    }),

    http.post(`${base}/bancos/:id/exclusoes`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const dados = (await request.json()) as { numeros: number[]; revisao_esperada: number };
      if (banco.estado === "congelado") {
        return erro(
          409,
          `O banco ${banco.versao} está congelado: a janela de exclusões fechou.`,
          "JANELA_EXCLUSOES_FECHADA",
        );
      }
      const conflito = revisaoDesatualizada(banco, dados.revisao_esperada);
      if (conflito) return conflito;
      const alvos = ativasDe(banco).filter((q) => dados.numeros.includes(q.numero));
      if (alvos.length !== new Set(dados.numeros).size) {
        return erro(
          422,
          `Nenhuma exclusão foi aplicada: ${dados.numeros.join(", ")} não pode(m) ser excluído(s).`,
          "NUMEROS_INVALIDOS",
        );
      }
      for (const q of alvos) q.estado = "excluida";
      return registrar(banco, "exclusao");
    }),

    http.post(`${base}/bancos/:id/congelar`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const dados = (await request.json()) as { revisao_esperada: number };
      const conflito = revisaoDesatualizada(banco, dados.revisao_esperada);
      if (conflito) return conflito;
      if (banco.estado === "congelado") {
        return erro(409, `O banco ${banco.versao} já está congelado.`, "BANCO_CONGELADO");
      }
      if (ativasDe(banco).length === 0) {
        return erro(409, `O banco ${banco.versao} não tem nenhuma questão ativa para congelar.`, "BANCO_VAZIO");
      }
      banco.estado = "congelado";
      return registrar(banco, "congelamento");
    }),

    http.post(`${base}/bancos/:id/questoes/:numero/substituicao`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const numero = Number(params.numero);
      const original = ativasDe(banco).find((q) => q.numero === numero);
      if (!original) {
        return erro(409, `A questão ${numero} não está ativa e não pode ser substituída.`, "ESTADO_QUESTAO_INVALIDO");
      }
      if (banco.questoes.some((q) => q.numero === numero && q.estado === "candidata")) {
        return erro(
          409,
          `A questão ${numero} já tem uma candidata pendente. Aceite ou rejeite antes de pedir outra.`,
          "CANDIDATA_PENDENTE",
        );
      }
      if (banco.versao.startsWith("insuf")) {
        const proposta: PropostaSubstituicao = {
          numero,
          candidata: null,
          motivo_insuficiencia: "o material não sustenta outra questão sobre este trecho",
          localizacao: original.fontes[0]?.localizacao ?? null,
        };
        return HttpResponse.json(proposta);
      }
      const candidata: Questao = {
        ...original,
        estado: "candidata",
        enunciado: `Variação do enunciado da questão ${numero}.`,
      };
      banco.questoes.push(candidata);
      const proposta: PropostaSubstituicao = { numero, candidata };
      return HttpResponse.json(proposta, { status: 201 });
    }),

    http.post(`${base}/bancos/:id/questoes/:numero/substituicao/aceitar`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const numero = Number(params.numero);
      const dados = (await request.json()) as { revisao_esperada: number };
      const candidata = banco.questoes.find((q) => q.numero === numero && q.estado === "candidata");
      if (!candidata) {
        return erro(409, `A questão ${numero} não tem candidata pendente.`, "SEM_CANDIDATA_PENDENTE");
      }
      const conflito = revisaoDesatualizada(banco, dados.revisao_esperada);
      if (conflito) return conflito;
      const original = ativasDe(banco).find((q) => q.numero === numero);
      if (original) original.estado = "substituida";
      candidata.estado = "ativa";
      return registrar(banco, "substituicao");
    }),

    http.post(`${base}/bancos/:id/questoes/:numero/substituicao/rejeitar`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const numero = Number(params.numero);
      const candidata = banco.questoes.find((q) => q.numero === numero && q.estado === "candidata");
      if (!candidata) {
        return erro(409, `A questão ${numero} não tem candidata pendente.`, "SEM_CANDIDATA_PENDENTE");
      }
      candidata.estado = "descartada";
      return HttpResponse.json({ numero, decisao: "rejeitada" });
    }),

    http.get(`${base}/bancos/:id/provas`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      if (!banco.provas) {
        return erro(
          404,
          `O banco ${banco.versao} ainda não tem provas montadas.`,
          "PROVAS_NAO_MONTADAS",
        );
      }
      return HttpResponse.json(montadasFalsas(banco, banco.provas));
    }),

    http.post(`${base}/bancos/:id/provas`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const dados = (await request.json()) as {
        n_objetivas: number;
        n_discursivas: number;
        revisao_esperada: number;
      };
      const conflito = revisaoDesatualizada(banco, dados.revisao_esperada);
      if (conflito) return conflito;
      if (banco.estado !== "congelado") {
        return erro(
          409,
          `O banco ${banco.versao} não está congelado. Congele antes de montar as provas.`,
          "BANCO_NAO_CONGELADO",
        );
      }
      if (banco.provas) {
        return erro(
          409,
          "A sessão já tem prova nas versões A, B. Remontar está fora do escopo.",
          "PROVAS_JA_MONTADAS",
        );
      }
      const ativas = ativasDe(banco);
      const doTipo = (tipo: Questao["tipo"]) => ativas.filter((q) => q.tipo === tipo);
      if (
        dados.n_objetivas > doTipo("objetiva").length ||
        dados.n_discursivas > doTipo("discursiva").length
      ) {
        const disponivel: Record<string, number> = {};
        for (const tipo of ["objetiva", "discursiva"] as const) {
          for (const faixa of FAIXAS) {
            disponivel[`${tipo}/${faixa}`] = doTipo(tipo).filter(
              (q) => q.faixa_dificuldade === faixa,
            ).length;
          }
        }
        return erro(
          409,
          "O banco não sustenta duas provas com essa distribuição. Reduza N, mude pF/pM/pD, ou substitua questões para reequilibrar as faixas.",
          "BANCO_INSUFICIENTE_PARA_PROVA",
          {
            // O falso não distribui por faixa: a cota inteira vai para "media".
            cotas_por_faixa: {
              facil: 0,
              media: dados.n_objetivas + dados.n_discursivas,
              dificil: 0,
            },
            pedido_por_tipo: { objetiva: dados.n_objetivas, discursiva: dados.n_discursivas },
            disponivel_por_celula: disponivel,
          },
        );
      }
      const provas = montarFalso(banco, dados.n_objetivas, dados.n_discursivas);
      return HttpResponse.json(montadasFalsas(banco, provas), { status: 201 });
    }),

    http.get(`${base}/provas/:id`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const id = Number(params.id);
      for (const sessao of estado.sessoes) {
        const banco = sessao.banco;
        if (!banco?.provas) continue;
        for (const versao of ["A", "B"] as const) {
          if (idDaProva(banco, versao) === id) {
            return HttpResponse.json(provaLida(banco, banco.provas, versao));
          }
        }
      }
      return erro(404, `Prova ${id} não encontrada.`, "PROVA_NAO_ENCONTRADA");
    }),

    http.post(`${base}/bancos/:id/auditoria`, async ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      const auditoria = (banco.auditoria ??= auditoriaFalsa());
      const limite = Number(new URL(request.url).searchParams.get("limite")) || null;
      auditoria.chamadas += 1;
      auditoria.limites.push(limite);
      await delay(auditoria.atraso ?? 0);
      if (auditoria.falhaNa === auditoria.chamadas) {
        return erro(
          502,
          "O modelo devolveu uma resposta que o sistema não conseguiu usar. Tente de novo.",
          "RESPOSTA_LLM_INVALIDA",
        );
      }
      const jaAntes = auditadasDe(banco).length;
      const pendentes = objetivasAtivas(banco).filter(
        (q) => auditoria.feitas.get(q.numero) !== banco.revisao,
      );
      for (const q of limite ? pendentes.slice(0, limite) : pendentes) {
        auditoria.feitas.set(q.numero, banco.revisao);
      }
      return HttpResponse.json(resumoDaAuditoria(banco, jaAntes));
    }),

    http.get(`${base}/bancos/:id/auditoria`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = bancoDe(params.id);
      if (!banco) return bancoNaoEncontrado(params.id);
      return HttpResponse.json(resumoDaAuditoria(banco, null));
    }),

    http.get(`${base}/prompts`, ({ request }) => {
      const docente = docenteDoToken(request);
      if (!docente) return naoAutorizado();
      if (docente.perfil !== "administrador") return proibido();
      return HttpResponse.json([...estado.prompts].reverse());
    }),

    http.post(`${base}/prompts`, async ({ request }) => {
      const docente = docenteDoToken(request);
      if (!docente) return naoAutorizado();
      if (docente.perfil !== "administrador") return proibido();
      const dados = (await request.json()) as PromptCriar;
      if (estado.prompts.some((p) => p.versao === dados.versao)) {
        return erro(409, `A versão ${dados.versao} já existe.`, "VERSAO_PROMPT_DUPLICADA");
      }
      const prompt: Prompt = {
        id: estado.prompts.length + 1,
        versao: dados.versao,
        papel_definido: dados.papel_definido,
        conteudo: `Texto montado para ${dados.disciplina} (${dados.periodo}), K=${dados.k_alternativas}.`,
        hash_modulos: "0".repeat(64),
        ativo: false,
        criado_em: new Date().toISOString(),
      };
      estado.prompts.push(prompt);
      return HttpResponse.json(prompt, { status: 201 });
    }),

    http.post(`${base}/prompts/:versao/ativar`, ({ request, params }) => {
      const docente = docenteDoToken(request);
      if (!docente) return naoAutorizado();
      if (docente.perfil !== "administrador") return proibido();
      const alvo = estado.prompts.find((p) => p.versao === params.versao);
      if (!alvo) {
        return erro(404, `Versão ${String(params.versao)} não encontrada.`, "VERSAO_PROMPT_NAO_ENCONTRADA");
      }
      for (const p of estado.prompts) p.ativo = p === alvo;
      return HttpResponse.json(alvo);
    }),

    // O back-end falso não grava eventos: a tela de log abre vazia.
    http.get(`${base}/admin/logs`, ({ request }) => {
      const docente = docenteDoToken(request);
      if (!docente) return naoAutorizado();
      if (docente.perfil !== "administrador") return proibido();
      return HttpResponse.json([]);
    }),
  ];
}
