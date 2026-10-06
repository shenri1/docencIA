import { Link } from "@tanstack/react-router";
import { CascaPublica } from "./CascaPublica";

// Os mesmos nomes das telas: quem lê aqui reconhece o fluxo depois de entrar.
const PASSOS = [
  {
    titulo: "Enviar materiais",
    texto: "PDF, PPTX, DOCX ou TXT da disciplina. Você confere o índice antes de seguir.",
  },
  {
    titulo: "Gerar o banco",
    texto:
      "Até 25 questões, objetivas e discursivas, distribuídas entre fácil, média e difícil conforme os percentuais da sessão.",
  },
  {
    titulo: "Revisar",
    texto:
      "Você exclui o que não serve, pede variação de uma questão e congela o banco quando ele estiver pronto.",
  },
  {
    titulo: "Auditar as objetivas",
    texto:
      "Opcional: uma segunda leitura aponta alternativa errada que o material também sustenta e distrator fácil demais de eliminar.",
  },
  {
    titulo: "Montar as provas A e B",
    texto:
      "Duas versões com as letras redistribuídas, verificadas quanto a colisão de letras e sobreposição de subtema.",
  },
  {
    titulo: "Gabaritos e DOCX",
    texto: "Gabarito simples e comentado, e dois arquivos DOCX com o sha256 de cada um.",
  },
];

// Cada garantia com a regra que a sustenta: nada aqui vai além do que o sistema faz.
const GARANTIAS = [
  {
    regra: "R2",
    texto:
      "Usa só os materiais que você enviou na sessão — nem conhecimento geral do modelo, nem busca externa.",
  },
  {
    regra: "",
    texto:
      "Quando o material não sustenta uma questão, responde “insuficiência de fonte” em vez de inventar.",
  },
  {
    regra: ", ",
    texto: "Cada questão traz o material, a localização e o trecho que a sustenta.",
  },
  { regra: "", texto: "Nada muda no banco sem um comando seu." },
  { regra: "", texto: "A exportação reproduz fielmente o que você aprovou." },
];

const LIMITES = [
  "Não é um chat.",
  "Não edita enunciados.",
  "Não busca na internet.",
  "Exporta só DOCX.",
  "Não se integra a ambientes virtuais de aprendizagem (LMS).",
];

/** só texto factual, sem depoimentos. */
export function Landing() {
  return (
    <CascaPublica>
      <div className="flex flex-col gap-14">
        <section className="flex max-w-3xl flex-col gap-5">
          <h1 className="font-serifa text-titulo">
            Bancos de questões a partir dos seus materiais, com a fonte de cada questão.
          </h1>
          <p className="font-serifa text-corpo-lg">
            Você envia os materiais da disciplina. O sistema gera questões objetivas e
            discursivas sustentadas por trechos deles, e você decide o que fica.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/cadastro" className="botao botao-primario">
              Criar conta
            </Link>
            <Link to="/login" className="botao botao-fantasma">
              Entrar
            </Link>
          </div>
        </section>

        <section aria-labelledby="como-funciona" className="flex flex-col gap-5">
          <h2 id="como-funciona" className="font-serifa text-subtitulo">
            Como funciona
          </h2>
          <ol className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {PASSOS.map((passo, i) => (
              <li key={passo.titulo} className="cartao flex flex-col gap-2 p-5">
                <span className="tabular font-grotesca text-detalhe text-texto-suave">
                  {i + 1}
                </span>
                <h3 className="font-serifa text-corpo-lg">{passo.titulo}</h3>
                <p className="font-grotesca text-detalhe">{passo.texto}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="garantias" className="flex flex-col gap-5">
          <h2 id="garantias" className="font-serifa text-subtitulo">
            O que o sistema garante
          </h2>
          <ul className="flex flex-col gap-4">
            {GARANTIAS.map((garantia) => (
              <li key={garantia.regra} className="flex flex-col gap-1 border-l-2 border-manter pl-4">
                <span className="font-serifa text-corpo-lg">{garantia.texto}</span>
                <span className="font-grotesca text-detalhe text-texto-suave">
                  {garantia.regra}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="limites" className="flex flex-col gap-5">
          <h2 id="limites" className="font-serifa text-subtitulo">
            O que ele não faz
          </h2>
          <ul className="list-disc pl-5 font-grotesca">
            {LIMITES.map((limite) => (
              <li key={limite}>{limite}</li>
            ))}
          </ul>
          <p className="max-w-3xl font-serifa text-corpo-lg">
            As questões são geradas por um modelo de linguagem. A revisão é sua: o sistema
            propõe, mede e registra, e quem decide é você.
          </p>
        </section>
      </div>
    </CascaPublica>
  );
}
