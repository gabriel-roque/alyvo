# Contêineres — C4

```mermaid
flowchart TB
  Browser --> Web[Next.js]
  Web --> API[FastAPI]
  API --> PG[(PostgreSQL)]
  API --> MinIO[(MinIO)]
  API --> Neo4j[(Neo4j)]
  API --> LLM[OpenRouter / Ollama]
  Worker[Celery worker] --> PG
  Beat[Celery beat] --> Redis[(Redis)]
  Redis --> Worker
  Worker --> Neo4j
  Worker --> MinIO
  Docs[Docusaurus] -. engenharia .-> Browser
```

Consulte [Responsabilidades dos componentes](component-responsibilities.md) para entender por que cada serviço existe, quais dados mantém e como participa dos principais fluxos.
