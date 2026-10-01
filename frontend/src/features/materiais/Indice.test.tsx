import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse, delay } from "msw";
import { server } from "../../mocks/server";
import {
  DOCENTE,
  umMarcoSessao,
  umMaterial,
  umaSessao,
} from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

const AULA = umMaterial({
  id: 1,
  identificador_curto: "S1",
  nome_arquivo: "aula-01.pptx",
  tipo: "slide",
  formato: "pptx",
  contagem_paginas_logicas: 24,
  origem_texto: "nativo",
  tamanho_bytes: 2_097_152,
});
const APOSTILA = umMaterial({
  id: 2,
  identificador_curto: "P1",
  nome_arquivo: "apostila.pdf",
  tipo: "pdf",
  formato: "pdf",
  contagem_paginas_logicas: 80,
  origem_texto: "misto",
  tamanho_bytes: 5_242_880,
});

/** Backend com estado: remover e confirmar mudam o que as leituras seguintes devolvem. */
function backend(inicial = [AULA, APOSTILA]) {
  let materiais = [...inicial];
  let confirmado = false;
  const chamadas = { removidos: [] as number[], confirmacoes: 0 };
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes/5`, () => HttpResponse.json(umaSessao({ id: 5 }))),
    http.get(`${API}/sessoes/5/marco`, () =>
      HttpResponse.json(
        umMarcoSessao({
          sessao_id: 5,
          marco: confirmado ? "m2_banco" : "m1_materiais",
          n_materiais: materiais.length,
        }),
      ),
    ),
    http.get(`${API}/sessoes/5/materiais/indice`, () =>
      HttpResponse.json({ materiais, confirmado }),
    ),
    http.delete(`${API}/sessoes/5/materiais/:id`, ({ params }) => {
      const id = Number(params.id);
      chamadas.removidos.push(id);
      materiais = materiais.filter((m) => m.id !== id);
      return new HttpResponse(null, { status: 204 });
    }),
    http.post(`${API}/sessoes/5/materiais/confirmar`, async () => {
      chamadas.confirmacoes += 1;
      // Folga para o teste enxergar o estado "indexando" antes da resposta.
      await delay(300);
      confirmado = true;
      return HttpResponse.json({ materiais, confirmado });
    }),
  );
  return chamadas;
}

describe("Índice de materiais", () => {
  it("lista os materiais com identificador, páginas, origem do texto e tamanho", async () => {
    backend();
    renderApp("/sessoes/5/indice", { token: "t" });

    const linha = (await screen.findByText("aula-01.pptx")).closest("tr")!;
    expect(within(linha).getByText("S1")).toBeInTheDocument();
    expect(within(linha).getByText("Slide")).toBeInTheDocument();
    expect(within(linha).getByText("PPTX")).toBeInTheDocument();
    expect(within(linha).getByText("24 slides")).toBeInTheDocument();
    expect(within(linha).getByText("texto nativo")).toBeInTheDocument();
    expect(within(linha).getByText("2,0 MB")).toBeInTheDocument();

    const outra = screen.getByText("apostila.pdf").closest("tr")!;
    expect(within(outra).getByText("P1")).toBeInTheDocument();
    expect(within(outra).getByText("texto nativo e OCR")).toBeInTheDocument();
  });

  it("remove um material e a tabela se atualiza", async () => {
    const chamadas = backend();
    const { user } = renderApp("/sessoes/5/indice", { token: "t" });

    await user.click(await screen.findByRole("button", { name: "Remover aula-01.pptx" }));

    await waitFor(() =>
      expect(screen.queryByText("aula-01.pptx")).not.toBeInTheDocument(),
    );
    expect(chamadas.removidos).toEqual([1]);
    expect(screen.getByText("apostila.pdf")).toBeInTheDocument();
  });

  it("mostra a recusa da API ao remover", async () => {
    backend();
    server.use(
      http.delete(`${API}/sessoes/5/materiais/:id`, () =>
        HttpResponse.json(
          {
            detail:
              "Operação não permitida no estado atual da sessão: o índice de materiais já foi confirmado e está congelado.",
            codigo: "SESSAO_ESTADO_INVALIDO",
          },
          { status: 409 },
        ),
      ),
    );
    const { user } = renderApp("/sessoes/5/indice", { token: "t" });

    await user.click(await screen.findByRole("button", { name: "Remover aula-01.pptx" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/já foi confirmado/);
    expect(screen.getByText("aula-01.pptx")).toBeInTheDocument();
  });

  it("avisa que a confirmação congela o índice", async () => {
    backend();
    renderApp("/sessoes/5/indice", { token: "t" });

    expect(
      await screen.findByText(/não será mais possível enviar ou remover materiais/i),
    ).toBeInTheDocument();
  });

  it("confirma o índice, mostra que está indexando e vai à geração do banco", async () => {
    const chamadas = backend();
    const { user, router } = renderApp("/sessoes/5/indice", { token: "t" });

    await user.click(await screen.findByRole("button", { name: "Confirmar índice" }));

    expect(await screen.findByRole("status")).toHaveTextContent(/indexando/i);
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/geracao"),
    );
    expect(chamadas.confirmacoes).toBe(1);
  });

  it("mostra a falha de indexação sem sair da tela", async () => {
    backend();
    server.use(
      http.post(`${API}/sessoes/5/materiais/confirmar`, () =>
        HttpResponse.json(
          {
            detail: "Serviço de embedding indisponível: conexão recusada.",
            codigo: "FALHA_EMBEDDING",
          },
          { status: 502 },
        ),
      ),
    );
    const { user, router } = renderApp("/sessoes/5/indice", { token: "t" });

    await user.click(await screen.findByRole("button", { name: "Confirmar índice" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/embedding indisponível/);
    expect(router.state.location.pathname).toBe("/sessoes/5/indice");
    expect(screen.getByRole("button", { name: "Confirmar índice" })).toBeEnabled();
  });

  it("sem materiais, não deixa confirmar e leva de volta ao envio", async () => {
    backend([]);
    renderApp("/sessoes/5/indice", { token: "t" });

    expect(await screen.findByText(/Nenhum material enviado/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar índice" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Voltar aos materiais" })).toHaveAttribute(
      "href",
      "/sessoes/5/materiais",
    );
  });

  it("se o índice já foi confirmado, recarregar leva à próxima tela", async () => {
    server.use(
      http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
      http.get(`${API}/sessoes/5/marco`, () =>
        HttpResponse.json(umMarcoSessao({ sessao_id: 5, marco: "m2_banco" })),
      ),
      http.get(`${API}/sessoes/5/materiais/indice`, () =>
        HttpResponse.json({ materiais: [AULA], confirmado: true }),
      ),
    );
    const { router } = renderApp("/sessoes/5/indice", { token: "t" });

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/sessoes/5/geracao"),
    );
  });
});
