# AGENTS.md

Instruções para agentes de codificação (opencode, Claude Code e ferramentas compatíveis com o padrão AGENTS.md).

## Visão geral

API REST que gera questões avaliativas, objetivas e discursivas, com LLM e RAG sobre os materiais enviados pelo docente. O único ator é o docente universitário.

**Stack:** Python 3.14, FastAPI, PostgreSQL com pgvector, Docker Compose. `pint` e `latex2mathml` servem ao Núcleo Determinístico (cálculo com unidades e conversão de fórmulas). O cliente web em `frontend/` usa React, Vite, TypeScript, TanStack Query/Router, Tailwind v4, Vitest e o runtime bun. Ele segue os marcos do Orquestrador e não é um chat.

## Regra arquitetural

O sistema separa duas responsabilidades:

- **Núcleo Determinístico:** nunca chama LLM. Exemplos: método do maior resto, distribuição de letras, validação de parâmetros, renderização de DOCX, checagem de consistência de estado.
- **Núcleo Semântico:** orquestra as chamadas a LLM (Gerador, Crítico/Auditor, juiz de aderência), em services Python de `backend/app/services/`. O Orquestrador decide avançar ou parar só pelo estado gravado e não pertence a este núcleo.

Se uma funcionalidade nova do Núcleo Determinístico parecer precisar de LLM, o desenho está errado.

Depois que um item é aprovado, nenhuma renderização (provas, gabaritos, DOCX) chama LLM: tudo opera sobre dados já persistidos.

## Estrutura

```text
backend/app/
├── main.py         # cria o FastAPI(), inclui routers, registra exception handlers
├── handlers.py     # exception handlers HTTP
├── domain.py       # enums do vocabulário fechado do domínio
├── core/           # config, db, security
├── api/            # router, dependências e um arquivo por recurso em endpoints/
├── schemas/        # entrada e saída da API (Pydantic)
├── services/       # regra de negócio: determinístico, semântico e orquestração
├── models/         # persistência (ORM)
├── exceptions/     # hierarquia de exceções de domínio
└── prompt/         # módulos .md do prompt mestre e montagem determinística
```

```text
frontend/src/
├── api/            # schema.d.ts GERADO do openapi.json, cliente openapi-fetch
├── app/            # criarApp, AppRaiz, AppShell
├── auth/           # token na sessionStorage
├── components/     # componentes sem regra de negócio
├── features/       # uma pasta por área
├── lib/            # funções puras
├── mocks/          # backendFalso (MSW com estado)
├── tokens/         # tokens.css: única fonte dos valores visuais
├── test/           # setup, renderApp, fixtures
└── routes.tsx      # árvore de rotas
```

```text
avaliacao/          # avaliação offline (RAGAS, comparação de extratores): projeto uv próprio
```

Fluxo de uma requisição: `endpoint` → `schema` valida o formato → `service` → exceção de domínio → `handler` traduz para HTTP.

## Convenções

- **Controller sem regra de negócio.** Só parsing, chamada ao service e tradução de exceção.
- **Schema de resposta separado do model** quando há campo que nunca pode vazar, como a justificativa estruturada da questão.
- **Service pela natureza:** o nome e a docstring dizem se ele chama LLM (semântico) ou não (determinístico).
- **Exceção de negócio não é bug.** `InsuficienciaDeFonteException`, `InconsistenciaDeEstadoException` e afins são comportamento correto: só a mensagem ao docente precisa ser clara.
- **Frontend:** o estado do fluxo mora no servidor (`GET /sessoes/{id}/marco` decide a tela), e o front nunca recalcula regra do backend. Quando o contrato mudar, rode `bun run gen:openapi` e `bun run gen:api` em `frontend/`. Nenhum valor visual fora de `src/tokens/tokens.css` (exceção: o CSS do KaTeX, só em `.katex`).
- TDD é obrigatório, no backend e no frontend.

## Regras de negócio que nunca podem ser quebradas

- pF + pM + pD soma exatamente 100% antes de qualquer geração.
- A única fonte são os materiais que o docente enviou na sessão: nunca conhecimento geral do modelo nem busca externa.
- Questão sem trecho claro no material não é gerada: o sistema responde "insuficiência de fonte" e diz o que faltou.
- Depois da janela de exclusões, o banco é congelado: substituição só com comando explícito do docente.
- Toda questão carrega a fonte (material, localização e trecho-base) fora do enunciado e das alternativas.
- A exportação é a renderização fiel do estado persistido: nunca reescreve conteúdo aprovado.

## Ambiente

- Agentes de codificação não usam Docker nem conectam direto no Postgres. A suíte usa banco de teste isolado (conftest), e duplos para embeddings, reranker, provedor de LLM e juiz: nunca toca a rede.
- O Ollama roda no host. A cadeia de geração vive na tabela `provedores_llm`, e trocá-la é migração (escrita à mão), não variável de ambiente. Embeddings, reranker e juiz são configurados por variável de ambiente.
- `avaliacao/` roda num Python 3.12 ou 3.13 gerenciado pelo `uv`, nunca no 3.14 do sistema, e não importa `backend.app`.
- O frontend roda sem Docker, banco nem Ollama: `bun run dev:mocks`. O runtime é o bun.

```bash
uv run pytest                       # backend
uv run ruff check backend avaliacao
uvicorn backend.app.main:app --reload

cd frontend
bun install
bun run dev          # Vite na 5173; /api faz proxy para localhost:8000
bun run dev:mocks    # interface contra o back-end falso
bun run test
bun run typecheck
bun run gen:openapi  # regenera ../openapi.json
bun run gen:api      # regenera src/api/schema.d.ts

python dev.py start  # banco + backend + frontend
```
