# Alyvo

Alyvo é um MVP local-first de assistente administrativo multimodal para
clínicas, construído como projeto de portfólio. A demonstração combina agenda
transacional, autenticação por código temporário, OCR revisável, RAG/GraphRAG,
chat orquestrado e back office — sempre com dados sintéticos e sem diagnóstico,
prescrição ou triagem clínica.

## O que está demonstrável

- home pública responsiva e acessível no design system Editorial Premium;
- chat administrativo com roteamento, baixa confiança, fontes e SSE;
- consulta de disponibilidade no banco operacional e agendamento confirmado;
- prevenção de conflito por validação transacional e constraint GiST no PostgreSQL;
- OTP de paciente, RBAC de equipe e isolamento obrigatório por `tenant_id`;
- upload de documento privado, OCR por adapter, edição e confirmação explícita;
- ingestão institucional com revisão, aprovação, outbox e projeção no Neo4j;
- agenda, pacientes, tickets, documentos, conhecimento e grafo somente leitura;
- adapters reais para Ollama, OpenRouter, BGE-M3, PaddleOCR, Neo4j e Celery,
  com fallbacks determinísticos para testes rápidos.

## Arquitetura

```text
Next.js ──► FastAPI ──► PostgreSQL (fonte operacional)
   │            │  └──► LangGraph ─► LangChain/providers ─► Ollama/OpenRouter
   │            └─────► Redis/Celery ─► PaddleOCR/embeddings/MinIO
   └── contratos OpenAPI              └► Neo4j (grafo + vetores)
```

O PostgreSQL mantém pacientes, agenda, documentos, auditoria e outbox. O worker
consome eventos idempotentes e projeta somente conhecimento aprovado no Neo4j.
Documentos de pacientes nunca entram no GraphRAG institucional.

## Início rápido sem Docker

Requisitos: Python 3.10+, Node 22+, npm 10+.

```bash
cp .env.example .env
make setup
make seed
```

Em dois terminais:

```bash
make api
make web
```

Abra `http://localhost:3000`. O modo padrão usa SQLite e providers `mock`, mas
exercita os mesmos contratos dos providers reais.

Credenciais sintéticas:

- paciente: CPF `123.456.789-09`, código `123456`;
- administração: `admin@alyvo.local` / `alyvo-demo`;
- recepção: `recepcao@alyvo.local` / `alyvo-demo`.

## Ambiente completo com Docker

```bash
cp .env.example .env
make infra-up
```

A API cria o schema local e carrega o seed sintético idempotente na primeira
inicialização.

Serviços:

| Serviço | URL/porta |
| --- | --- |
| Web | `http://localhost:3000` |
| API / OpenAPI | `http://localhost:8000/docs` |
| Neo4j Browser | `http://localhost:7474` |
| MinIO Console | `http://localhost:9001` |
| Mailpit | `http://localhost:8025` |

Ollama fica em um perfil opcional para evitar download involuntário de modelos:

```bash
docker compose -f infra/docker-compose.yml --profile models up -d
docker compose -f infra/docker-compose.yml exec ollama ollama pull qwen3:8b
```

Depois, altere `LLM_PROVIDER=ollama`. Para OCR/embedding reais, instale
`pip install -e '.[ocr]'` e `sentence-transformers`, então use
`OCR_PROVIDER=paddle` e `EMBEDDING_PROVIDER=bge-m3`.

## Validação

```bash
make validate
```

O comando executa testes Python, integração, Ruff, testes web, TypeScript,
ESLint, build de produção, Playwright em desktop/mobile, validação do Compose e
geração do OpenAPI. O resultado fica em `reports/validation.json`.

Para também subir e verificar a infraestrutura pesada:

```bash
VALIDATE_WITH_INFRA=1 make validate
```

Comandos individuais:

```bash
make test-api
npm run typecheck
npm run build
npm run test:e2e
make openapi
docker compose -f infra/docker-compose.yml config --quiet
```

## Rotas principais

Frontend: `/`, `/chat`, `/agendar`, `/documentos/revisao`, `/backoffice`,
`/backoffice/agenda` e `/backoffice/conhecimento`.

API: prefixo `/api/v1`; consulte `packages/contracts/openapi.json` ou `/docs`.
Os contratos TypeScript consumidos pelo frontend ficam em
`packages/contracts/src/index.ts`.

## Limites conscientes do ambiente

Os testes automatizados usam SQLite e providers determinísticos para não baixar
modelos de vários gigabytes. A garantia de sobreposição concorrente em produção
é adicionada por `apps/api/migrations/0001_initial.sql`; a suíte isolada valida o
mesmo conflito no serviço. A execução real de PaddleOCR, BGE-M3, Ollama, MinIO e
Neo4j depende dos serviços/modelos locais descritos acima.

Consulte [PLAN.md](PLAN.md), [arquitetura](docs/ARCHITECTURE.md) e o
[design system](docs/design-system/README.md).

