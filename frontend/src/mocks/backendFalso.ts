/**
 * Back-end falso com estado, só para o front avançar sem API nem Ollama
 * e para os testes de fluxo. Reproduz o contrato e os erros de domínio 
 * (auth, sessões, materiais, índice); não reproduz regra de negócio além do
 * necessário para exercitar a interface.
 *
 * Gatilhos de teste manual: um arquivo cujo nome começa com "ilegivel" é recusado
 * como PDF sem texto extraível; extensão fora de PDF/PPTX/DOCX/TXT dá 415;
 * versão de banco começando com "lacuna" deixa o número 2 sem sustentação na
 * primeira tentativa; cadastrar a credencial "admin" cria um administrador (na
 * API real, ele vem da migração e1a4c8f02b77). O estado nasce com o prompt mestre
 * 1.0.0 ativo, como depois da migração.
 */
import { http, HttpResponse } from "msw";
import type {
  Banco,
  Docente,
  MarcoBanco,
  MarcoSessao,
  Material,
  Prompt,
  PromptCriar,
  ResumoBanco,
  Sessao,
} from "../api/tipos";

interface DocenteFalso extends Docente {
  senha: string;
}

interface BancoFalso {
  banco_id: number;
  versao: string;
  n_objetivas: number;
  n_discursivas: number;
  gerados: Set<number>;
  recusados: Set<number>;
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

const erro = (status: number, detail: string, codigo: string, extras = {}) =>
  HttpResponse.json({ detail, codigo, ...extras }, { status });

function marcoDoBanco(banco: BancoFalso): MarcoBanco {
  const n_alvo = banco.n_objetivas + banco.n_discursivas;
  return {
    versao: banco.versao,
    banco_id: banco.banco_id,
    revisao: 0,
    marco: "m3_exclusoes",
    motivo: null,
    n_alvo,
    n_atual: banco.gerados.size,
    lacunas: n_alvo - banco.gerados.size,
    alerta_desvio: false,
    objetivas_ativas: banco.gerados.size,
    objetivas_auditadas: 0,
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

    http.get(`${base}/bancos/:id`, ({ request, params }) => {
      if (!docenteDoToken(request)) return naoAutorizado();
      const banco = estado.sessoes.find((s) => s.banco?.banco_id === Number(params.id))?.banco;
      if (!banco) return erro(404, `Banco ${params.id} não encontrado.`, "BANCO_NAO_ENCONTRADO");
      const resposta: Banco = {
        banco_id: banco.banco_id,
        versao: banco.versao,
        revisao: 0,
        rotulo: `${banco.versao}.r0`,
        estado: "aberto",
        n_alvo: banco.n_objetivas + banco.n_discursivas,
        n_alvo_objetivas: banco.n_objetivas,
        n_alvo_discursivas: banco.n_discursivas,
        n_atual: banco.gerados.size,
        ultimo_relatorio: null,
        questoes: [],
      };
      return HttpResponse.json(resposta);
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
