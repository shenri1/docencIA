# docencIA

Geração de questões de prova a partir dos materiais do próprio docente.

O docencIA recebe os materiais de uma disciplina (PDF, DOCX, TXT), indexa o conteúdo e gera um banco de questões objetivas e discursivas com um modelo de linguagem local. Toda questão aponta o trecho do material que a sustenta. Do banco curado saem duas provas equivalentes (A e B), os gabaritos e os arquivos DOCX.

Projeto de TCC de Engenharia da Computação da UEMA.

> **Versão beta.** As questões são geradas por modelos locais pequenos e precisam de revisão do docente antes de qualquer aplicação.

## Funcionalidades

- **Materiais:** upload com checagem de legibilidade e OCR para PDF escaneado. O docente confirma o índice antes de gerar.
- **Só o material da sessão:** o modelo responde apenas com o que foi enviado, sem conhecimento geral nem busca externa. Quando o material não sustenta uma questão, o sistema registra "insuficiência de fonte" em vez de inventar.
- **Formatos:**
  - objetivas: proposição, análise de afirmativas, asserção-razão e cálculo numérico;
  - discursivas: com aspectos esperados, cada um com a sua fonte.
- **Dificuldade:** o banco segue os percentuais de fácil, média e difícil escolhidos pelo docente.
- **Revisão em duas camadas:** um agente crítico revisa cada rascunho, e um validador sem LLM confere as regras de elaboração do item.
- **Cálculo verificado:** o modelo propõe dados e expressão, e o sistema calcula o resultado e os distratores com checagem de unidades.
- **Fórmulas:** LaTeX na tela (KaTeX) e equação nativa do Word no DOCX.
- **Curadoria:**
  - leitura em blocos e exclusões com relatório de impacto;
  - congelamento do banco;
  - substituição guiada por orientações do docente;
  - auditoria sob comando.
- **Provas A e B:** distribuição balanceada de letras e de dificuldade, com gabaritos simples e comentados.
- **DOCX:** renderização fiel ao que foi aprovado, reproduzível byte a byte, em formato padrão de prova (A4, Arial, campos de identificação).
- **Métricas por questão:** tempo de cada etapa, tokens, candidatos da busca com os scores, checagem das citações e notas de aderência de um modelo juiz. São só registro, para análise.
- **Privacidade:** o log de auditoria guarda o ator por pseudônimo, nunca por nome ou credencial.

## Arquitetura

O backend separa duas responsabilidades:

- **Núcleo Determinístico:** nunca chama LLM. Distribuição por dificuldade, sorteio de letras, validação, cálculo, renderização de DOCX e checagem de consistência.
- **Núcleo Semântico:** as chamadas ao modelo, feitas pelo Gerador, pelo Crítico/Auditor e pelo juiz de aderência.

Depois que uma questão é aprovada, nada que a exibe ou exporta chama o modelo de novo.

| Camada | Tecnologia |
| --- | --- |
| API | Python 3.14, FastAPI, SQLAlchemy, Alembic |
| Banco | PostgreSQL com pgvector |
| Modelos | Ollama no host (geração, embeddings, reordenação e juiz) |
| Web | React, Vite, TypeScript, TanStack Query/Router, Tailwind v4, bun |
| Empacotamento | Docker Compose |

## Requisitos

- Docker e Docker Compose
- [Ollama](https://ollama.com) 0.12.11 ou mais recente, rodando no host, com os modelos:

  ```bash
  ollama pull qwen3.5:9b                          # geração (principal)
  ollama pull qwen3:4b                            # fallback da geração e juiz (em CPU)
  ollama pull qwen3:1.7b                          # fallback e reordenação da busca (em CPU)
  ollama pull dengcao/Qwen3-Embedding-0.6B:Q8_0   # embeddings
  ```

- Uma GPU com cerca de 8 GB de VRAM para o modelo principal

## Como rodar

```bash
cp .env.example .env
```

Edite o `.env` antes de subir:

- `SECRET_KEY` e `PSEUDONIMO_KEY`: valores próprios, gerados com `python -c "import secrets; print(secrets.token_hex(32))"`. Com os valores de exemplo, a API se recusa a subir.
- `POSTGRES_PASSWORD` e o `DATABASE_URL` correspondente.
- `ADMIN_CREDENCIAL`, `ADMIN_NOME` e `ADMIN_SENHA`: a conta de administrador criada na primeira migração.

```bash
docker compose -f infra/compose.yml up --build
```

A interface fica em **http://localhost:8080**. A API fica em `127.0.0.1:8000`, com a documentação interativa em `/docs`.

## Desenvolvimento

Pré-requisitos: [uv](https://docs.astral.sh/uv/), [bun](https://bun.sh) e Docker (só para o banco).

```bash
uv sync
cd frontend && bun install && cd ..

python dev.py start     # banco (Docker) + migrações + API (uvicorn) + web (Vite na 5173)
python dev.py status
python dev.py stop
```

Em máquina de desenvolvimento, `AMBIENTE=desenvolvimento` no `.env` aceita as chaves de exemplo.

A interface também roda sozinha, contra um back-end falso, sem banco nem Ollama:

```bash
cd frontend && bun run dev:mocks
```

### Testes

```bash
uv run pytest                 # backend (banco de teste isolado; LLM, embeddings e juiz são duplos)
uv run ruff check backend avaliacao

cd frontend
bun run test                  # Vitest + MSW
bun run typecheck
```

Quando o contrato da API mudar, regenere os tipos do frontend:

```bash
cd frontend
bun run gen:openapi           # ../openapi.json
bun run gen:api               # src/api/schema.d.ts
```

### Avaliação offline

`avaliacao/` é um projeto `uv` separado (Python 3.12 ou 3.13), com a avaliação por RAGAS e a comparação de extratores de PDF. Ele lê o banco por SQL e não faz parte da API:

```bash
uv run --project avaliacao python -m avaliacao.ragas_avaliar --sessao 1 --limite 5
```

## Estrutura

```text
backend/app/     API: endpoints, schemas, services, models, prompt
backend/alembic/ migrações
backend/tests/   suíte do backend
frontend/        cliente web
avaliacao/       avaliação offline
infra/           Docker Compose
dev.py           ambiente de desenvolvimento
```

## Limitações conhecidas

- Testado num único ambiente, com modelos locais pequenos. A qualidade depende do modelo e do material.
- Questões de cálculo com decibéis (dB) ainda não são suportadas: nesses casos, o sistema troca a questão de cálculo por uma proposição.
- O juiz de aderência roda em CPU e deixa a geração mais lenta. As notas dele ainda não foram comparadas com o julgamento de docentes.
- No DOCX, afirmativas justificadas podem sair com espaçamento irregular.
- Sem recuperação de senha por e-mail e sem exportação em PDF.
