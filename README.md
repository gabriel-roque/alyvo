# Alyvo

Assistente administrativo multimodal para clínicas, feito com dados sintéticos.
O projeto reúne chat com RAG/GraphRAG, agenda transacional, OCR revisável e um
backoffice. Não oferece diagnóstico, prescrição ou triagem.

## Executar

Requisitos: Docker com Compose e cerca de 12 GB livres para imagens e modelos.

```bash
docker compose up --build
```

Na primeira execução, o Compose baixa o `qwen3:8b` e o BGE-M3. Quando os
serviços estiverem saudáveis:

- aplicação: `http://localhost:3000`
- API e OpenAPI: `http://localhost:8000/docs`
- e-mails e códigos: `http://localhost:8025`
- Neo4j: `http://localhost:7474`
- MinIO: `http://localhost:9001`

Credenciais sintéticas:

- paciente: CPF `123.456.789-09`, código `123456`
- administração: `admin@alyvo.local` / `alyvo-demo`
- recepção: `recepcao@alyvo.local` / `alyvo-demo`

## Validar

Com a infraestrutura em execução:

```bash
docker compose --profile validation run --rm validate
```

A validação cobre testes Python e web, tipos, lint, build, migrações, RLS,
concorrência de agenda, outbox/Neo4j, OCR real, RAG/GraphRAG com Ragas e os
fluxos Playwright em desktop e mobile. O resultado fica em
`reports/validation.json`.

## Componentes

```text
Next.js ─► FastAPI ─► LangGraph/LangChain ─► Ollama
                ├──► PostgreSQL (operações e outbox)
                ├──► Redis/Celery ─► PaddleOCR + BGE-M3
                ├──► MinIO (arquivos privados)
                └──► Neo4j (grafo e vetores)
```

O PostgreSQL é a fonte de verdade. O worker projeta no Neo4j somente dados e
documentos aprovados. Documentos de pacientes nunca entram no conhecimento
compartilhado. O frontend usa os contratos gerados em `packages/contracts`.
