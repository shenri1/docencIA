import katex from "katex";
import "katex/dist/katex.min.css";
import { separar } from "../lib/formulas";

function formatar(latex: string, destaque: boolean): string | null {
  try {
    return katex.renderToString(latex, {
      trust: false,
      strict: "error",
      throwOnError: true,
      displayMode: destaque,
    });
  } catch {
    return null;
  }
}

interface Props {
  texto: string;
  className?: string;
  /** `span` dentro de linha (item de lista, rótulo); `p` é o padrão. */
  como?: "p" | "span";
}

/** Texto do modelo, com fórmula. Inválida volta crua, nunca escondida. */
export function TextoComFormulas({ texto, className, como: Tag = "p" }: Props) {
  return (
    <Tag className={`whitespace-pre-line ${className ?? ""}`.trim()}>
      {separar(texto).map((s, i) => {
        if (s.tipo === "texto") return <span key={i}>{s.conteudo}</span>;
        const html = formatar(s.latex, s.destaque);
        if (html === null) {
          return <span key={i}>{s.destaque ? `\\[${s.latex}\\]` : `\\(${s.latex}\\)`}</span>;
        }
        // Saída do KaTeX com trust: false: sem link, sem HTML do autor.
        return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />;
      })}
    </Tag>
  );
}
