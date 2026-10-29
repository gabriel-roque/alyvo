# Infraestrutura local

`docker compose -f infra/docker-compose.yml up --build` inicia PostgreSQL, Neo4j,
Redis, MinIO, Mailpit, API, worker e web. O perfil `models` adiciona Ollama:

```bash
docker compose -f infra/docker-compose.yml --profile models up -d
docker compose -f infra/docker-compose.yml exec ollama ollama pull qwen3:8b
```

O ambiente padrão usa provedores determinísticos (`mock`) para permitir uma demo
imediata sem baixar modelos. Defina `LLM_PROVIDER=ollama`, `OCR_PROVIDER=paddle`
e `EMBEDDING_PROVIDER=bge-m3` para ativar os adapters locais reais.

