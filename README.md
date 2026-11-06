# Alyvo

Assistente administrativo single-clinic para diretório médico, agenda, atendimento conversacional e conhecimento institucional. O backend é um monólito modular FastAPI; o frontend usa Next.js; processamento assíncrono usa Celery, outbox e projeção Neo4j.

> O Alyvo não oferece diagnóstico, prescrição ou triagem. Todos os seeds e exemplos são sintéticos.

## Quickstart

```bash
cp .env.example .env
docker compose up --build -d
```

- Web: <http://localhost:3000>
- API/Scalar: <http://localhost:8000/docs>
- OpenAPI: <http://localhost:8000/openapi.json>
- Portal de engenharia: <http://localhost:8001>
- Readiness: <http://localhost:8000/health/ready>

## Desenvolvimento

```bash
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run pytest
npm ci
npm run typecheck && npm run lint && npm run build
npm run build:docs
```

Consulte os [primeiros passos](docs/getting-started.md), a [arquitetura](docs/architecture/overview.md) e os [ADRs](docs/decisions/0001-modular-monolith.md).
