import { Link, useRouter } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { PASSOS_NOVA_SESSAO, Passos } from "../../components/Passos";
import { somaDosPercentuais } from "../../lib/validacao";
import { useCriarSessao } from "./api";

const K_MIN = 2;
const K_MAX = 11;

function inteiroEntre(texto: string, min: number, max: number): number | null {
  if (texto.trim() === "") return null;
  const n = Number(texto);
  return Number.isInteger(n) && n >= min && n <= max ? n : null;
}

export function NovaSessao() {
  const router = useRouter();
  const criar = useCriarSessao();
  const [disciplina, setDisciplina] = useState("");
  const [periodo, setPeriodo] = useState("");
  const [tema, setTema] = useState("");
  const [area, setArea] = useState("");
  const [k, setK] = useState("5");
  const [pF, setPF] = useState("10");
  const [pM, setPM] = useState("60");
  const [pD, setPD] = useState("30");
  const [tentou, setTentou] = useState(false);

  const kValido = inteiroEntre(k, K_MIN, K_MAX);
  const f = inteiroEntre(pF, 0, 100);
  const m = inteiroEntre(pM, 0, 100);
  const d = inteiroEntre(pD, 0, 100);
  const percentuaisValidos = f !== null && m !== null && d !== null;
  const soma = percentuaisValidos ? somaDosPercentuais(f, m, d) : null;
  // Conveniência de formato: quem decide a soma é a API.
  const somaFecha = soma === 100;

  const erros = {
    disciplina: disciplina.trim() ? null : "Informe a disciplina.",
    periodo: periodo.trim()
      ? null
      : "Informe o período letivo, por exemplo 2026.2.",
    k: kValido !== null ? null : `Use de ${K_MIN} a ${K_MAX} alternativas.`,
  };
  const erroPercentual = (v: number | null) =>
    v !== null ? null : "Use um número inteiro de 0 a 100.";

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    setTentou(true);
    if (Object.values(erros).some(Boolean) || !somaFecha) return;
    criar.mutate(
      {
        disciplina: disciplina.trim(),
        periodo: periodo.trim(),
        tema_escopo: tema.trim() || null,
        area_do_conhecimento: area.trim() || null,
        k_alternativas: kValido!,
        p_f: f!,
        p_m: m!,
        p_d: d!,
      },
      {
        onSuccess: (sessao) =>
          void router.navigate({
            to: "/sessoes/$sessaoId/materiais",
            params: { sessaoId: String(sessao.id) },
          }),
      },
    );
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6">
      <div className="flex flex-col gap-3">
        <h1 className="font-serifa text-titulo">Nova sessão</h1>
        <Passos passos={PASSOS_NOVA_SESSAO} atual={1} />
      </div>

      {criar.error && <Alerta variante="erro">{criar.error.message}</Alerta>}

      <form noValidate onSubmit={enviar} className="folha flex flex-col gap-5 p-6">
        <Campo
          rotulo="Disciplina"
          value={disciplina}
          maxLength={255}
          onChange={(e) => setDisciplina(e.target.value)}
          erro={tentou ? erros.disciplina : null}
        />
        <Campo
          rotulo="Período letivo"
          ajuda="Por exemplo, 2026.2."
          value={periodo}
          maxLength={50}
          onChange={(e) => setPeriodo(e.target.value)}
          erro={tentou ? erros.periodo : null}
        />
        <Campo
          rotulo="Tema ou escopo (opcional)"
          ajuda="O recorte que a avaliação cobre."
          value={tema}
          maxLength={500}
          onChange={(e) => setTema(e.target.value)}
        />
        <Campo
          rotulo="Área do conhecimento (opcional)"
          value={area}
          maxLength={255}
          onChange={(e) => setArea(e.target.value)}
        />
        <Campo
          rotulo="Alternativas por questão (K)"
          type="number"
          min={K_MIN}
          max={K_MAX}
          value={k}
          onChange={(e) => setK(e.target.value)}
          erro={tentou ? erros.k : null}
        />

        <fieldset className="flex flex-col gap-3">
          <legend className="font-grotesca text-rotulo-lg">
            Distribuição por dificuldade
          </legend>
          <div className="grid grid-cols-3 gap-3">
            <Campo
              rotulo="Fáceis (%)"
              type="number"
              min={0}
              max={100}
              value={pF}
              onChange={(e) => setPF(e.target.value)}
              erro={tentou ? erroPercentual(f) : null}
            />
            <Campo
              rotulo="Médias (%)"
              type="number"
              min={0}
              max={100}
              value={pM}
              onChange={(e) => setPM(e.target.value)}
              erro={tentou ? erroPercentual(m) : null}
            />
            <Campo
              rotulo="Difíceis (%)"
              type="number"
              min={0}
              max={100}
              value={pD}
              onChange={(e) => setPD(e.target.value)}
              erro={tentou ? erroPercentual(d) : null}
            />
          </div>
          <p
            role="status"
            className={`tabular font-grotesca text-detalhe ${
              somaFecha ? "text-manter" : "text-descartar"
            }`}
          >
            Soma: {soma ?? "—"}%
            {!somaFecha && " — precisa ser 100%"}
          </p>
        </fieldset>

        <div className="flex items-center justify-end gap-3">
          <Link to="/" className="botao botao-fantasma">
            Cancelar
          </Link>
          <Botao type="submit" disabled={!somaFecha || criar.isPending}>
            {criar.isPending ? "Criando…" : "Criar sessão e continuar"}
          </Botao>
        </div>
      </form>
    </div>
  );
}
