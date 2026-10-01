/**
 * Back-end falso com estado, só para o front avançar sem API nem Ollama
 * e para os testes de fluxo. Reproduz o contrato e os erros de domínio 
 * (auth, sessões, materiais, índice); não reproduz regra de negócio além do
 * necessário para exercitar a interface.
 *
 * Gatilhos de teste manual: um arquivo cujo nome começa com "ilegivel" é recusado
 * como PDF sem texto extraível; extensão fora de PDF/PPTX/DOCX/TXT dá 415.
 */
import { http, HttpResponse } from "msw";
import type { Docente, Material, MarcoSessao, Sessao } from "../api/tipos";

interface DocenteFalso extends Docente {
  senha: string;
}

interface SessaoFalsa extends Sessao {
  materiais: Material[];
}

export interface EstadoFalso {
  docentes: DocenteFalso[];
  sessoes: SessaoFalsa[];
  proximoMaterial: number;
}

export function novoEstado(): EstadoFalso {
  return { docentes: [], sessoes: [], proximoMaterial: 1 };
}

const PREFIXO: Record<Material["tipo"], string> = { slide: "S", pdf: "P", livro: "L" };
const FORMATOS = ["pdf", "pptx", "docx", "txt"] as const;

const erro = (status: number, detail: string, codigo: string, extras = {}) =>
  HttpResponse.json({ detail, codigo, ...extras }, { status });

export function criarHandlers(base: string, estado: EstadoFalso = novoEstado()) {
  const docenteDoToken = (request: Request) => {
    const token = request.headers.get("authorization")?.replace("Bearer ", "");
    const id = Number(token?.replace("mock-token-", ""));
    return estado.docentes.find((d) => d.id === id);
  };
  const naoAutorizado = () =>
    erro(401, "Token inválido ou expirado.", "TOKEN_INVALIDO");
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
        perfil: "docente",
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
        estado.sessoes.slice(offset, offset + limit).map(({ materiais: _m, ...s }) => s),
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
      const { materiais: _m, ...resposta } = sessao;
      return HttpResponse.json(resposta, { status: 201 });
    }),

    http.get(`${base}/sessoes/:id`, ({ request, params }) => {
      const sessao = sessaoDe(params.id);
      if (!docenteDoToken(request)) return naoAutorizado();
      if (!sessao) return erro(404, `Sessão ${params.id} não encontrada.`, "SESSAO_NAO_ENCONTRADA");
      const { materiais: _m, ...resposta } = sessao;
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
        bancos: [],
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
  ];
}
