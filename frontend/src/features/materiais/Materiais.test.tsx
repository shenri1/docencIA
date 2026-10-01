import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse, delay } from "msw";
import { server } from "../../mocks/server";
import {
  DOCENTE,
  umIndice,
  umMarcoSessao,
  umMaterial,
  umaSessao,
} from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

function backend({
  marco = umMarcoSessao({ sessao_id: 5 }),
  indice = umIndice(),
}: {
  marco?: ReturnType<typeof umMarcoSessao>;
  indice?: ReturnType<typeof umIndice>;
} = {}) {
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes/5`, () => HttpResponse.json(umaSessao({ id: 5 }))),
    http.get(`${API}/sessoes/5/marco`, () => HttpResponse.json(marco)),
    http.get(`${API}/sessoes/5/materiais/indice`, () => HttpResponse.json(indice)),
  );
}

function arquivo(nome: string, conteudo = "conteudo") {
  return new File([conteudo], nome);
}

async function escolher(
  user: ReturnType<typeof renderApp>["user"],
  ...arquivos: File[]
) {
  const entrada = await screen.findByLabelText("Selecionar arquivos");
  await user.upload(entrada, arquivos);
}

async function definirTipo(
  user: ReturnType<typeof renderApp>["user"],
  nomeDoArquivo: string,
  tipo: "slide" | "pdf" | "livro",
) {
  const linha = (await screen.findByText(nomeDoArquivo)).closest("li")!;
  await user.selectOptions(within(linha).getByLabelText(/Tipo didático/), tipo);
}

describe("Materiais — envio", () => {
  it("se o índice já foi confirmado, recarregar leva à próxima tela", async () => {
    backend({ marco: umMarcoSessao({ sessao_id: 5, marco: "m2_banco" }) });
    const { router } = renderApp("/sessoes/5/materiais", { token: "t" });

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/geracao"),
    );
  });

  it("só aceita os formatos que a API aceita", async () => {
    backend();
    renderApp("/sessoes/5/materiais", { token: "t" });

    expect(await screen.findByLabelText("Selecionar arquivos")).toHaveAttribute(
      "accept",
      ".pdf,.pptx,.docx,.txt",
    );
  });

  it("não envia sem o tipo didático de cada arquivo", async () => {
    backend();
    const { user } = renderApp("/sessoes/5/materiais", { token: "t" });

    await escolher(user, arquivo("aula-01.pptx"), arquivo("livro.pdf"));
    expect(screen.getByRole("button", { name: "Enviar arquivos" })).toBeDisabled();

    await definirTipo(user, "aula-01.pptx", "slide");
    expect(screen.getByRole("button", { name: "Enviar arquivos" })).toBeDisabled();

    await definirTipo(user, "livro.pdf", "livro");
    expect(screen.getByRole("button", { name: "Enviar arquivos" })).toBeEnabled();
  });

  it("envia cada arquivo como multipart, um por vez, e mostra o resultado", async () => {
    backend();
    const recebidos: { tipo: unknown; nome: string }[] = [];
    let ativos = 0;
    let maximoSimultaneo = 0;
    server.use(
      http.post(`${API}/sessoes/5/materiais`, async ({ request }) => {
        ativos += 1;
        maximoSimultaneo = Math.max(maximoSimultaneo, ativos);
        const form = await request.formData();
        const enviado = form.get("arquivo") as File;
        recebidos.push({ tipo: form.get("tipo"), nome: enviado.name });
        await delay(20);
        ativos -= 1;
        return HttpResponse.json(
          umMaterial({
            id: recebidos.length,
            identificador_curto: recebidos.length === 1 ? "S1" : "P1",
            nome_arquivo: enviado.name,
            formato: enviado.name.endsWith(".pptx") ? "pptx" : "pdf",
            contagem_paginas_logicas: recebidos.length === 1 ? 24 : 1,
            origem_texto: recebidos.length === 1 ? "nativo" : "ocr",
          }),
          { status: 201 },
        );
      }),
    );
    const { user } = renderApp("/sessoes/5/materiais", { token: "t" });

    await escolher(user, arquivo("aula-01.pptx"), arquivo("apostila.pdf"));
    await definirTipo(user, "aula-01.pptx", "slide");
    await definirTipo(user, "apostila.pdf", "pdf");
    await user.click(screen.getByRole("button", { name: "Enviar arquivos" }));

    const aula = (await screen.findByText("aula-01.pptx")).closest("li")!;
    expect(await within(aula).findByText(/S1 · 24 slides · texto nativo/)).toBeInTheDocument();
    const apostila = screen.getByText("apostila.pdf").closest("li")!;
    expect(await within(apostila).findByText(/P1 · 1 página · reconhecido por OCR/)).toBeInTheDocument();

    expect(recebidos).toEqual([
      { tipo: "slide", nome: "aula-01.pptx" },
      { tipo: "pdf", nome: "apostila.pdf" },
    ]);
    expect(maximoSimultaneo).toBe(1);
  });

  it("mostra a causa da recusa, os formatos aceitos, e segue com os outros arquivos", async () => {
    backend();
    server.use(
      http.post(`${API}/sessoes/5/materiais`, async ({ request }) => {
        const form = await request.formData();
        const enviado = form.get("arquivo") as File;
        if (enviado.name === "escaneado.pdf") {
          return HttpResponse.json(
            {
              detail:
                "Não foi possível extrair texto confiável deste PDF, nem com OCR. Envie uma versão com texto selecionável.",
              codigo: "PDF_OCR_INSUFICIENTE",
              motivo: "pouco texto reconhecido",
              paginas_afetadas: [3, 5],
            },
            { status: 422 },
          );
        }
        return HttpResponse.json(
          umMaterial({ nome_arquivo: enviado.name, identificador_curto: "S1" }),
          { status: 201 },
        );
      }),
    );
    const { user } = renderApp("/sessoes/5/materiais", { token: "t" });

    await escolher(user, arquivo("escaneado.pdf"), arquivo("aula.pptx"));
    await definirTipo(user, "escaneado.pdf", "pdf");
    await definirTipo(user, "aula.pptx", "slide");
    await user.click(screen.getByRole("button", { name: "Enviar arquivos" }));

    const recusado = (await screen.findByText("escaneado.pdf")).closest("li")!;
    expect(await within(recusado).findByText(/Não foi possível extrair texto/)).toBeInTheDocument();
    expect(within(recusado).getByText(/Páginas afetadas: 3, 5/)).toBeInTheDocument();
    expect(within(recusado).getByText(/Formatos aceitos: PDF, PPTX, DOCX e TXT/)).toBeInTheDocument();
    const aceito = screen.getByText("aula.pptx").closest("li")!;
    expect(await within(aceito).findByText(/S1/)).toBeInTheDocument();
  });

  it("mostra o aviso de arquivo repetido", async () => {
    backend();
    server.use(
      http.post(`${API}/sessoes/5/materiais`, () =>
        HttpResponse.json(
          {
            detail: "Este arquivo já foi enviado nesta sessão como S1.",
            codigo: "MATERIAL_DUPLICADO",
            identificador_curto: "S1",
          },
          { status: 409 },
        ),
      ),
    );
    const { user } = renderApp("/sessoes/5/materiais", { token: "t" });

    await escolher(user, arquivo("aula.pptx"));
    await definirTipo(user, "aula.pptx", "slide");
    await user.click(screen.getByRole("button", { name: "Enviar arquivos" }));

    expect(await screen.findByText(/já foi enviado nesta sessão como S1/)).toBeInTheDocument();
  });

  it("aceita arquivos arrastados e deixa tirar da fila antes de enviar", async () => {
    backend();
    const { user } = renderApp("/sessoes/5/materiais", { token: "t" });

    const zona = await screen.findByTestId("zona-de-arquivos");
    fireEvent.drop(zona, { dataTransfer: { files: [arquivo("solto.txt")] } });

    expect(await screen.findByText("solto.txt")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tirar solto.txt da fila" }));
    expect(screen.queryByText("solto.txt")).not.toBeInTheDocument();
  });

  it("segue para o índice quando já há materiais enviados", async () => {
    backend({ indice: umIndice([umMaterial(), umMaterial({ id: 2, identificador_curto: "P1" })]) });
    const { user, router } = renderApp("/sessoes/5/materiais", { token: "t" });

    expect(await screen.findByText(/2 materiais já enviados/)).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Continuar para o índice" }));

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/indice"),
    );
  });

  it("sem material enviado, não há como seguir para o índice", async () => {
    backend();
    renderApp("/sessoes/5/materiais", { token: "t" });

    await screen.findByLabelText("Selecionar arquivos");
    expect(screen.queryByRole("link", { name: "Continuar para o índice" })).not.toBeInTheDocument();
  });
});
