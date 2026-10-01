import { useState, type FormEvent } from "react";
import type { Prompt } from "../../api/tipos";
import { Alerta } from "../../components/Alerta";
import { Botao } from "../../components/Botao";
import { Campo } from "../../components/Campo";
import { inteiroEntre } from "../../lib/validacao";
import { usePrompts, useAtivarPrompt, useRegistrarPrompt } from "./api";

// Os mesmos marcadores da migração e1a4c8f02b77: estes campos só entram no texto
// gravado para auditoria; a geração reinjeta os parâmetros da sessão.
const PAPEL_PADRAO = "docente universitário elaborador de questões";
const DISCIPLINA_MARCADOR = "(definida em cada sessão)";
const PERIODO_MARCADOR = "(definido em cada sessão)";

const data = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function Prompts() {
  const prompts = usePrompts();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="font-serifa text-subtitulo">Prompt mestre</h2>
        <p className="font-grotesca text-detalhe text-texto-suave">
          A versão ativa é a que toda geração, revisão e auditoria usa. Registrar não
          ativa: ativar é um passo separado, e é por ele que se volta a uma versão
          anterior.
        </p>
      </div>

      {prompts.isError && <Alerta variante="erro">{prompts.error.message}</Alerta>}
      {prompts.isPending && (
        <p className="font-grotesca text-detalhe text-texto-suave">Carregando versões…</p>
      )}
      {prompts.data && prompts.data.length === 0 && (
        <Alerta variante="aviso">
          Nenhuma versão registrada. Sem uma versão ativa, nenhum banco pode ser gerado.
        </Alerta>
      )}
      {prompts.data && prompts.data.length > 0 && (
        <ul className="flex flex-col gap-3">
          {prompts.data.map((prompt) => (
            <LinhaPrompt key={prompt.id} prompt={prompt} />
          ))}
        </ul>
      )}

      <FormularioPrompt />
    </div>
  );
}

function LinhaPrompt({ prompt }: { prompt: Prompt }) {
  const ativar = useAtivarPrompt();
  const [confirmando, setConfirmando] = useState(false);

  return (
    <li className="cartao flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="tabular font-serifa text-subtitulo">{prompt.versao}</span>
          {prompt.ativo && <span className="chip">Ativa</span>}
        </div>
        {!prompt.ativo && !confirmando && (
          <Botao
            variante="fantasma"
            aria-label={`Ativar ${prompt.versao}`}
            onClick={() => setConfirmando(true)}
          >
            Ativar
          </Botao>
        )}
      </div>
      <p className="flex flex-wrap gap-x-3 gap-y-1 font-grotesca text-detalhe text-texto-suave">
        <span>{prompt.papel_definido}</span>
        <span className="tabular">{data.format(new Date(prompt.criado_em))}</span>
        <span>
          Hash dos módulos:{" "}
          <span className="tabular" title={prompt.hash_modulos}>
            {prompt.hash_modulos.slice(0, 12)}
          </span>
        </span>
      </p>

      {confirmando && (
        <div className="flex flex-col gap-3">
          <Alerta variante="aviso">
            Ativar a versão {prompt.versao}? Todas as próximas gerações, revisões e
            auditorias passam a usar este texto.
          </Alerta>
          {ativar.error && <Alerta variante="erro">{ativar.error.message}</Alerta>}
          <div className="flex justify-end gap-3">
            <Botao variante="fantasma" onClick={() => setConfirmando(false)}>
              Cancelar
            </Botao>
            <Botao
              disabled={ativar.isPending}
              onClick={() =>
                ativar.mutate(prompt.versao, { onSuccess: () => setConfirmando(false) })
              }
            >
              {ativar.isPending ? "Ativando…" : "Confirmar ativação"}
            </Botao>
          </div>
        </div>
      )}

      <details className="font-grotesca text-detalhe">
        <summary className="cursor-pointer">Ver o texto enviado ao modelo</summary>
        <pre className="mt-2 whitespace-pre-wrap break-words">{prompt.conteudo}</pre>
      </details>
    </li>
  );
}

function FormularioPrompt() {
  const registrar = useRegistrarPrompt();
  const [versao, setVersao] = useState("");
  const [papel, setPapel] = useState(PAPEL_PADRAO);
  const [disciplina, setDisciplina] = useState(DISCIPLINA_MARCADOR);
  const [periodo, setPeriodo] = useState(PERIODO_MARCADOR);
  const [k, setK] = useState("5");
  const [registrada, setRegistrada] = useState<string | null>(null);

  const kValido = inteiroEntre(k, 2, 11);
  const valido =
    versao.trim() !== "" &&
    papel.trim() !== "" &&
    disciplina.trim() !== "" &&
    periodo.trim() !== "" &&
    kValido !== null;

  function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!valido) return;
    setRegistrada(null);
    registrar.mutate(
      {
        versao: versao.trim(),
        papel_definido: papel.trim(),
        disciplina: disciplina.trim(),
        periodo: periodo.trim(),
        k_alternativas: kValido,
        n_faceis: 0,
        n_medias: 0,
        n_dificeis: 0,
      },
      {
        onSuccess: (prompt) => {
          setRegistrada(prompt.versao);
          setVersao("");
        },
      },
    );
  }

  return (
    <form noValidate onSubmit={enviar} className="folha flex flex-col gap-5 p-6">
      <h3 className="font-serifa text-corpo-lg">Registrar versão</h3>
      <p className="font-grotesca text-detalhe text-texto-suave">
        O texto é montado a partir dos módulos em disco. Disciplina, período e K só
        entram no texto gravado para auditoria; cada geração usa os da sua sessão.
      </p>

      {registrar.error && <Alerta variante="erro">{registrar.error.message}</Alerta>}
      {registrada && (
        <Alerta variante="sucesso">
          Versão {registrada} registrada. Ela nasce inativa: ative quando quiser usá-la.
        </Alerta>
      )}

      <Campo
        rotulo="Versão"
        ajuda="Por exemplo, 1.1.0."
        value={versao}
        maxLength={50}
        onChange={(e) => setVersao(e.target.value)}
      />
      <Campo
        rotulo="Papel do modelo"
        value={papel}
        maxLength={255}
        onChange={(e) => setPapel(e.target.value)}
      />
      <div className="grid gap-3 sm:grid-cols-3">
        <Campo
          rotulo="Disciplina"
          value={disciplina}
          maxLength={255}
          onChange={(e) => setDisciplina(e.target.value)}
        />
        <Campo
          rotulo="Período"
          value={periodo}
          maxLength={50}
          onChange={(e) => setPeriodo(e.target.value)}
        />
        <Campo
          rotulo="Alternativas (K)"
          type="number"
          min={2}
          max={11}
          value={k}
          onChange={(e) => setK(e.target.value)}
        />
      </div>
      <div className="flex justify-end">
        <Botao type="submit" disabled={!valido || registrar.isPending}>
          {registrar.isPending ? "Registrando…" : "Registrar versão"}
        </Botao>
      </div>
    </form>
  );
}
