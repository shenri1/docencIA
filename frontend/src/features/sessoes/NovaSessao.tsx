import { Link, useRouter } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { PASSOS_NOVA_SESSAO, Passos } from "../../components/Passos";
import { inteiroEntre, somaDosPercentuais } from "../../lib/validacao";
import { TETO_ATIVAS, useOrientacoesDaUltimaSessao } from "../orientacoes/api";
import { useCriarSessao } from "./api";

const K_MIN = 2;
const K_MAX = 11;
// Espelha MAX_K_COM_CALCULO de backend/app/schemas/sessao.py. Conveniência:
// a API continua sendo a autoridade.
const K_MAX_COM_CALCULO = 5;

export function NovaSessao() {
  const ultima = useOrientacoesDaUltimaSessao();
  // O pré-preenchimento é conveniência: se a leitura falhar, o formulário abre vazio.
  if (ultima.isPending) {
    return <p className="font-grotesca text-detalhe text-texto-suave">Carregando…</p>;
  }
  return <FormularioNovaSessao trazidas={ultima.data ?? []} />;
}

function FormularioNovaSessao({ trazidas }: { trazidas: string[] }) {
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
  const [pCalculo, setPCalculo] = useState("0");
  const [tentou, setTentou] = useState(false);
  const [orientacoes, setOrientacoes] = useState<string[]>(trazidas.length ? trazidas : [""]);
  const trocarOrientacao = (i: number, valor: string) =>
    setOrientacoes((atual) => atual.map((t, j) => (j === i ? valor : t)));
  const removerOrientacao = (i: number) =>
    setOrientacoes((atual) => atual.filter((_, j) => j !== i));

  const kValido = inteiroEntre(k, K_MIN, K_MAX);
  const f = inteiroEntre(pF, 0, 100);
  const m = inteiroEntre(pM, 0, 100);
  const d = inteiroEntre(pD, 0, 100);
  const calculo = inteiroEntre(pCalculo, 0, 100);
  const calculoExigeKMenor =
    calculo !== null && calculo > 0 && kValido !== null && kValido > K_MAX_COM_CALCULO;
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
    if (calculo === null || calculoExigeKMenor) return;
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
        p_calculo: calculo,
        orientacoes: orientacoes.map((t) => t.trim()).filter(Boolean),
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

        <div className="flex flex-col gap-2">
          <Campo
            rotulo="Questões de cálculo (%)"
            ajuda="Percentual das objetivas que são de cálculo numérico. O sistema calcula as alternativas; use 0 para disciplinas sem cálculo."
            type="number"
            min={0}
            max={100}
            value={pCalculo}
            onChange={(e) => setPCalculo(e.target.value)}
            erro={tentou ? erroPercentual(calculo) : null}
          />
          {calculoExigeKMenor && (
            <p role="alert" className="font-grotesca text-detalhe text-descartar">
              Questões de cálculo exigem no máximo {K_MAX_COM_CALCULO} alternativas.
            </p>
          )}
        </div>

        <fieldset className="flex flex-col gap-3">
          <legend className="font-grotesca text-rotulo-lg">
            Como você costuma elaborar provas
          </legend>
          <p className="font-grotesca text-detalhe text-texto-suave">
            Opcional. Preferências que valem para todas as questões desta sessão, como “prefiro
            exemplos práticos”. Elas nunca ampliam a fonte além do material que você enviar.
          </p>
          {trazidas.length > 0 && (
            <p className="font-grotesca text-detalhe text-texto-suave">
              Trazidas da sua última sessão.
            </p>
          )}
          {orientacoes.map((texto, i) => (
            <div key={i} className="flex items-end gap-3">
              <div className="min-w-0 flex-1">
                <Campo
                  rotulo={`Orientação ${i + 1}`}
                  value={texto}
                  maxLength={500}
                  onChange={(e) => trocarOrientacao(i, e.target.value)}
                />
              </div>
              <Botao
                variante="fantasma"
                aria-label={`Remover orientação ${i + 1}`}
                onClick={() => removerOrientacao(i)}
              >
                Remover
              </Botao>
            </div>
          ))}
          <div>
            <Botao
              variante="fantasma"
              disabled={orientacoes.length >= TETO_ATIVAS}
              onClick={() => setOrientacoes((atual) => [...atual, ""])}
            >
              Acrescentar orientação
            </Botao>
          </div>
        </fieldset>

        <div className="flex items-center justify-end gap-3">
          <Link to="/sessoes" className="botao botao-fantasma">
            Cancelar
          </Link>
          <Botao type="submit" disabled={!somaFecha || calculoExigeKMenor || criar.isPending}>
            {criar.isPending ? "Criando…" : "Criar sessão e continuar"}
          </Botao>
        </div>
      </form>
    </div>
  );
}
