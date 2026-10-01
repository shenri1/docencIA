import { screen, waitFor, within } from "@testing-library/react";
import { API, renderApp } from "../test/renderApp";
import { criarHandlers, novoEstado } from "./backendFalso";
import { server } from "./server";

/**
 * Critério de aceitação, contra o back-end falso:
 * criar conta, entrar, criar sessão, ver a recusa de um PDF ilegível com a
 * causa, confirmar o índice e chegar à tela de geração.
 */
describe("fluxo contra o back-end falso", () => {
  // Fluxo longo com muita digitação simulada: o limite padrão de 5 s fica na borda.
  it("do cadastro à tela de geração, e recarregar volta ao mesmo marco", { timeout: 20_000 }, async () => {
    server.use(...criarHandlers(API));
    const { user, router } = renderApp("/cadastro");

    // Cadastro
    await user.type(await screen.findByLabelText("Nome completo"), "Ana Souza");
    await user.type(screen.getByLabelText("Credencial institucional"), "ana.souza");
    await user.type(screen.getByLabelText("Senha"), "segredo123");
    await user.click(screen.getByRole("checkbox", { name: /LGPD/ }));
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    // Login
    await user.type(await screen.findByLabelText("Credencial institucional"), "ana.souza");
    await user.type(screen.getByLabelText("Senha"), "segredo123");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByText("Você ainda não criou nenhuma sessão.")).toBeInTheDocument();

    // Nova sessão: parâmetros
    await user.click(screen.getByRole("link", { name: "Criar primeira sessão" }));
    await user.type(await screen.findByLabelText("Disciplina"), "Algoritmos");
    await user.type(screen.getByLabelText("Período letivo"), "2026.2");
    await user.click(screen.getByRole("button", { name: "Criar sessão e continuar" }));

    // Materiais: um PDF ilegível e uma apresentação
    const entrada = await screen.findByLabelText("Selecionar arquivos");
    await user.upload(entrada, [
      new File(["x"], "ilegivel.pdf"),
      new File(["x"], "aula-01.pptx"),
    ]);
    const linhaPdf = (await screen.findByText("ilegivel.pdf")).closest("li")!;
    const linhaPptx = screen.getByText("aula-01.pptx").closest("li")!;
    await user.selectOptions(within(linhaPdf).getByLabelText(/Tipo didático/), "pdf");
    await user.selectOptions(within(linhaPptx).getByLabelText(/Tipo didático/), "slide");
    await user.click(screen.getByRole("button", { name: "Enviar arquivos" }));

    expect(await within(linhaPdf).findByText(/Causa: /)).toBeInTheDocument();
    expect(within(linhaPdf).getByText(/Formatos aceitos/)).toBeInTheDocument();
    expect(await within(linhaPptx).findByText(/S1/)).toBeInTheDocument();

    // Índice: confirma
    await user.click(await screen.findByRole("link", { name: "Continuar para o índice" }));
    await user.click(await screen.findByRole("button", { name: "Confirmar índice" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toMatch(/\/sessoes\/\d+\/banco$/),
    );
    expect(await screen.findByRole("heading", { name: "Geração do banco" })).toBeInTheDocument();

    // Recarregar na tela de materiais: o servidor diz que já passou do M1
    const caminhoBanco = router.state.location.pathname;
    const sessaoId = caminhoBanco.split("/")[2] ?? "";
    await router.navigate({ to: "/sessoes/$sessaoId/materiais", params: { sessaoId } });
    await waitFor(() => expect(router.state.location.pathname).toBe(caminhoBanco));
  });

  it("recusa credencial já cadastrada como a API faz", async () => {
    const estado = novoEstado();
    estado.docentes.push({
      id: 1,
      nome: "Ana",
      credencial_institucional: "ana",
      perfil: "docente",
      senha: "segredo123",
    });
    server.use(...criarHandlers(API, estado));
    const { user } = renderApp("/cadastro");

    await user.type(await screen.findByLabelText("Nome completo"), "Outra Ana");
    await user.type(screen.getByLabelText("Credencial institucional"), "ana");
    await user.type(screen.getByLabelText("Senha"), "segredo123");
    await user.click(screen.getByRole("checkbox", { name: /LGPD/ }));
    await user.click(screen.getByRole("button", { name: "Criar conta" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/já cadastrada/);
  });

  it("recusa a senha errada sem entrar", async () => {
    const estado = novoEstado();
    estado.docentes.push({
      id: 1,
      nome: "Ana",
      credencial_institucional: "ana",
      perfil: "docente",
      senha: "segredo123",
    });
    server.use(...criarHandlers(API, estado));
    const { user, router } = renderApp("/login");

    await user.type(await screen.findByLabelText("Credencial institucional"), "ana");
    await user.type(screen.getByLabelText("Senha"), "errada1234");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Credenciais inválidas.");
    expect(router.state.location.pathname).toBe("/login");
  });
});
