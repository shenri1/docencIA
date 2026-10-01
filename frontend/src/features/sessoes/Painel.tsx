import { Link, useNavigate } from "@tanstack/react-router";
import type { Sessao } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { TAMANHO_PAGINA, useMarcoSessao, useSessoes } from "./api";
import { proximaAcao } from "./proximaAcao";

const ROTULO_ESTADO: Record<Sessao["estado"], string> = {
  rascunho: "Rascunho",
  materiais_confirmados: "Materiais confirmados",
  banco_gerado: "Banco gerado",
  banco_congelado: "Banco congelado",
  provas_montadas: "Provas montadas",
  exportado: "Exportado",
};

function ProximaAcao({ sessaoId }: { sessaoId: number }) {
  const marco = useMarcoSessao(sessaoId);
  if (marco.isPending) {
    return <span className="text-texto-suave">Consultando andamento…</span>;
  }
  if (marco.isError) {
    return (
      <span className="text-texto-suave">
        Não foi possível consultar o andamento.
      </span>
    );
  }
  return <span className="font-semibold">{proximaAcao(marco.data)}</span>;
}

function LinhaSessao({ sessao }: { sessao: Sessao }) {
  return (
    <li className="cartao flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <Link
          to="/sessoes/$sessaoId"
          params={{ sessaoId: String(sessao.id) }}
          className="font-serifa text-subtitulo underline-offset-4 hover:underline"
        >
          {sessao.disciplina}
        </Link>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-grotesca text-detalhe text-texto-suave">
          <span className="tabular">{sessao.periodo}</span>
          {sessao.tema_escopo && <span>{sessao.tema_escopo}</span>}
          <span className="chip">{ROTULO_ESTADO[sessao.estado]}</span>
        </p>
      </div>
      <p className="font-grotesca text-detalhe">
        <ProximaAcao sessaoId={sessao.id} />
      </p>
    </li>
  );
}

export function Painel({ pagina }: { pagina: number }) {
  const navigate = useNavigate();
  const sessoes = useSessoes(pagina);
  const irParaPagina = (nova: number) =>
    void navigate({ to: "/", search: { pagina: nova === 1 ? undefined : nova } });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-4">
        <h1 className="font-serifa text-titulo">Minhas sessões</h1>
        {sessoes.data && sessoes.data.length > 0 && (
          <Link to="/sessoes/nova" className="botao botao-primario">
            Nova sessão
          </Link>
        )}
      </div>

      {sessoes.isError && <Alerta variante="erro">{sessoes.error.message}</Alerta>}
      {sessoes.isPending && (
        <p className="font-grotesca text-detalhe text-texto-suave">
          Carregando sessões…
        </p>
      )}

      {sessoes.data && sessoes.data.length === 0 && pagina === 1 && (
        <div className="cartao flex flex-col items-start gap-4 p-6">
          <p className="font-serifa text-corpo-lg">
            Você ainda não criou nenhuma sessão.
          </p>
          <p className="font-grotesca text-detalhe text-texto-suave">
            Uma sessão reúne a disciplina, os materiais e o banco de questões de
            uma avaliação.
          </p>
          <Link to="/sessoes/nova" className="botao botao-primario">
            Criar primeira sessão
          </Link>
        </div>
      )}

      {sessoes.data && sessoes.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {sessoes.data.map((sessao) => (
            <LinhaSessao key={sessao.id} sessao={sessao} />
          ))}
        </ul>
      )}

      {sessoes.data && (pagina > 1 || sessoes.data.length === TAMANHO_PAGINA) && (
        <nav aria-label="Paginação" className="flex items-center gap-3">
          <Botao
            variante="fantasma"
            disabled={pagina === 1}
            onClick={() => irParaPagina(pagina - 1)}
          >
            Página anterior
          </Botao>
          <span className="tabular font-grotesca text-detalhe text-texto-suave">
            Página {pagina}
          </span>
          <Botao
            variante="fantasma"
            disabled={sessoes.data.length < TAMANHO_PAGINA}
            onClick={() => irParaPagina(pagina + 1)}
          >
            Próxima página
          </Botao>
        </nav>
      )}
    </div>
  );
}
