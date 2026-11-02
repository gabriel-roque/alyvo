# Alyvo

Assistente administrativo multimodal para clínicas, feito com dados sintéticos.
O projeto reúne chat anônimo com RAG/GraphRAG e function calling, agenda
transacional e um backoffice enxuto. Não oferece diagnóstico, prescrição ou triagem.

## Executar

Requisitos: Docker com Compose, GPU NVIDIA com pelo menos 8 GB, NVIDIA Container
Toolkit e cerca de 12 GB livres para imagens e modelos. Valide o host antes de subir:

```bash
bash scripts/gpu-preflight.sh
```

```bash
docker compose up --build
```

Na primeira execução, o Compose baixa o `qwen3:8b-q4_K_M` e o BGE-M3. Configure
`OPENROUTER_API_KEY` e `OPENROUTER_MODEL` para usar o OpenRouter como provedor
primário. Se ele estiver indisponível ou não configurado, o LangChain usa o
Ollama local como fallback. O Ollama mantém o modelo aquecido, com contexto de
4.096 tokens, Flash Attention e cache KV quantizado. Quando os
serviços estiverem saudáveis:

- aplicação: `http://localhost:3000`
- API e OpenAPI: `http://localhost:8000/docs`
- Neo4j: `http://localhost:7474`
- MinIO: `http://localhost:9001`

Credenciais sintéticas:

- paciente: CPF `123.456.789-09`, nascimento `15/01/1990`
- administração: `admin@alyvo.local` / `alyvo-demo`
- recepção: `recepcao@alyvo.local` / `alyvo-demo`

## Validar

Com a infraestrutura em execução:

```bash
docker compose --profile validation run --rm validate
```

A validação cobre testes Python e web, tipos, lint, build, migrações, RLS,
concorrência de agenda, outbox/Neo4j, OCR na ingestão de conhecimento,
RAG/GraphRAG e fluxos Playwright em 375, 768, 1024 e 1440 px. O resultado fica em
`reports/validation.json`.

Para medir latência aquecida, concorrência e confirmar que o modelo está 100% na
GPU:

```bash
docker compose --profile validation run --rm validate python3 scripts/benchmark-chat.py
```

O relatório fica em `reports/performance.json`.

## Componentes

```text
Next.js ─► FastAPI ─► LangGraph ─► LangChain ─► OpenRouter
                │          │             └──► Ollama (fallback)
                │          └──► LangSmith (traces desidentificados, opcional)
                ├──► PostgreSQL (operações, checkpoints e outbox)
                ├──► Redis/Celery ─► PaddleOCR + BGE-M3
                ├──► MinIO (arquivos privados)
                └──► Neo4j (grafo e vetores)
```

O PostgreSQL é a fonte de verdade. O worker projeta no Neo4j somente dados e
documentos institucionais aprovados. O frontend usa os contratos gerados em
`packages/contracts`.

O tracing externo fica desligado por padrão. Para ativá-lo, configure
`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY` e `LANGSMITH_PROJECT`. Entradas são
desidentificadas antes de entrar no grafo e fluxos sensíveis registram apenas
metadados operacionais.

Detalhes: [arquitetura](docs/ARCHITECTURE.md) e [roteiro de demonstração](docs/DEMO.md).
