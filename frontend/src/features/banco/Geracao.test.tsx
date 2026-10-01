import { screen, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import {
  DOCENTE,
  umBanco,
  umMarcoBanco,
  umMarcoSessao,
  umResumoBanco,
} from "../../test/fixtures";
import { API, renderApp } from "../../test/renderApp";

interface Corpo {
  versao: string;
  n_objetivas: number;
  n_discursivas: number;
  apos: number;
  limite: number;
}

/**
 * Sessão 5 com um banco que a API gera um número por chamada (limite 1).
 * `improdutivos` nunca ganham questão; `falhaNa` faz a chamada N cair na rede.
 */
function backend({
  total = 3,
  improdutivos = [] as number[],
  jaGerados = [] as number[],
  atraso = 0,
  falhaNa = 0,
  conflitoNa = 0,
} = {}) {
  const gerados = new Set(jaGerados);
  let existe = jaGerados.length > 0;
  const corpos: Corpo[] = [];
  const numeros = Array.from({ length: total }, (_, i) => i + 1);
  server.use(
    http.get(`${API}/auth/me`, () => HttpResponse.json(DOCENTE)),
    http.get(`${API}/sessoes/5/marco`, () =>
      HttpResponse.json(
        umMarcoSessao({
          sessao_id: 5,
          marco: "m2_banco",
          n_materiais: 1,
          bancos: existe
            ? [
                umMarcoBanco({
                  banco_id: 7,
                  versao: "v1",
                  n_alvo: total,
                  n_atual: gerados.size,
                  lacunas: total - gerados.size,
                }),
              ]
            : [],
        }),
      ),
    ),
    http.get(`${API}/bancos/7`, () =>
      HttpResponse.json(
        umBanco({
          banco_id: 7,
          versao: "v1",
          n_alvo: total,
          n_alvo_objetivas: total - 1,
          n_alvo_discursivas: 1,
        }),
      ),
    ),
    http.post(`${API}/sessoes/5/banco`, async ({ request }) => {
      const corpo = (await request.json()) as Corpo;
      corpos.push(corpo);
      if (corpos.length === falhaNa) return HttpResponse.error();
      if (corpos.length === conflitoNa) {
        return HttpResponse.json(
          {
            detail:
              "Outra requisição já gravou a questão 2 do banco v1: há uma geração em andamento para ele.",
            codigo: "GERACAO_EM_ANDAMENTO",
          },
          { status: 409 },
        );
      }
      await delay(atraso);
      existe = true;
      const proximo = numeros.find((n) => n > corpo.apos && !gerados.has(n)) ?? null;
      const improdutivo = proximo !== null && improdutivos.includes(proximo);
      if (proximo !== null && !improdutivo) gerados.add(proximo);
      const restantes =
        proximo === null ? 0 : numeros.filter((n) => n > proximo && !gerados.has(n)).length;
      return HttpResponse.json(
        umResumoBanco({
          banco_id: 7,
          geradas: proximo !== null && !improdutivo ? 1 : 0,
          improdutivas: improdutivo
            ? [{ numero: proximo, localizacao: "página 3", motivo: "o trecho não define o termo" }]
            : [],
          ultimo_numero: proximo,
          restantes,
        }),
        { status: 201 },
      );
    }),
  );
  return { corpos };
}

async function preencherEGerar(
  user: ReturnType<typeof renderApp>["user"],
  objetivas: string,
  discursivas = "0",
) {
  const campoObj = await screen.findByLabelText("Questões objetivas");
  await user.clear(campoObj);
  await user.type(campoObj, objetivas);
  const campoDisc = screen.getByLabelText("Questões discursivas");
  await user.clear(campoDisc);
  await user.type(campoDisc, discursivas);
  await user.click(screen.getByRole("button", { name: "Gerar banco" }));
}

describe("Geração do banco", () => {
  it("valida o total de 1 a 25 antes de enviar", async () => {
    backend();
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    const campoObj = await screen.findByLabelText("Questões objetivas");
    await user.clear(campoObj);
    await user.type(campoObj, "26");
    expect(screen.getByRole("button", { name: "Gerar banco" })).toBeDisabled();
    await user.clear(campoObj);
    await user.type(campoObj, "0");
    expect(screen.getByRole("button", { name: "Gerar banco" })).toBeDisabled();
  });

  it("gera em laço, uma questão por chamada, até restantes = 0", async () => {
    const { corpos } = backend({ total: 3, improdutivos: [2] });
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    await preencherEGerar(user, "3");

    expect(await screen.findByText("2 questões geradas nesta rodada.")).toBeInTheDocument();
    expect(corpos.map((c) => [c.apos, c.limite])).toEqual([
      [0, 1],
      [1, 1],
      [2, 1],
    ]);
    expect(corpos[0]).toMatchObject({ versao: "v1", n_objetivas: 3, n_discursivas: 0 });
    // Improdutiva mostrada uma vez, com número e motivo.
    expect(screen.getByText(/Questão 2 \(página 3\): o trecho não define o termo/)).toBeInTheDocument();
    // O marco, relido, diz que ficou uma lacuna.
    expect(await screen.findByText("Falta 1 questão no banco v1.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continuar geração" })).toBeInTheDocument();
  });

  it("mostra o progresso vindo da API", async () => {
    backend({ total: 3, atraso: 80 });
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    await preencherEGerar(user, "3");

    expect(await screen.findByText("Gerando a primeira questão…")).toBeInTheDocument();
    expect(await screen.findByText("Questão 1 de 3 concluída")).toBeInTheDocument();
    // Espera o laço terminar: um laço solto chamaria o handler do teste seguinte.
    expect(await screen.findByText("3 questões geradas nesta rodada.")).toBeInTheDocument();
  });

  it("pausar para depois da chamada em curso", async () => {
    const { corpos } = backend({ total: 5, atraso: 80 });
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    await preencherEGerar(user, "5");
    await screen.findByText("Questão 1 de 5 concluída");
    await user.click(screen.getByRole("button", { name: "Pausar geração" }));

    expect(await screen.findByText("Faltam 3 questões no banco v1.")).toBeInTheDocument();
    expect(corpos).toHaveLength(2);
  });

  it("erro de rede pausa o laço e oferece continuar", async () => {
    backend({ total: 3, falhaNa: 2 });
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    await preencherEGerar(user, "3");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Não foi possível falar com o servidor/,
    );
    expect(await screen.findByRole("button", { name: "Continuar geração" })).toBeInTheDocument();
  });

  it("409 de geração em andamento para o laço e mostra a mensagem da API", async () => {
    const { corpos } = backend({ total: 3, conflitoNa: 2 });
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    await preencherEGerar(user, "3");

    expect(await screen.findByRole("alert")).toHaveTextContent(/geração em andamento/);
    expect(corpos).toHaveLength(2);
  });

  it("continuar lê as contagens do banco e retoma do início", async () => {
    const { corpos } = backend({ total: 3, jaGerados: [1, 3] });
    const { user } = renderApp("/sessoes/5/geracao", { token: "t" });

    await user.click(await screen.findByRole("button", { name: "Continuar geração" }));

    await waitFor(() => expect(corpos).toHaveLength(1));
    expect(corpos[0]).toEqual({
      versao: "v1",
      n_objetivas: 2,
      n_discursivas: 1,
      apos: 0,
      limite: 1,
    });
    expect(await screen.findByText(/O banco v1 está completo/)).toBeInTheDocument();
  });

  it("seguir para a curadoria com lacunas leva a /banco", async () => {
    backend({ total: 3, jaGerados: [1] });
    renderApp("/sessoes/5/geracao", { token: "t" });

    expect(
      await screen.findByRole("link", { name: "Seguir para a curadoria com 2 lacunas" }),
    ).toHaveAttribute("href", "/sessoes/5/banco");
  });

  it("banco completo oferece seguir para a curadoria", async () => {
    backend({ total: 2, jaGerados: [1, 2] });
    renderApp("/sessoes/5/geracao", { token: "t" });

    expect(await screen.findByText(/O banco v1 está completo, com 2 questões/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Seguir para a curadoria" })).toHaveAttribute(
      "href",
      "/sessoes/5/banco",
    );
  });
});
