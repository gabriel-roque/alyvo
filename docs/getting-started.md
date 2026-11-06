# Primeiros passos

Requisitos: Docker Compose, Node 22 e `uv`. Copie `.env.example` para `.env` e use valores locais.

```bash
docker compose up --build -d
```

Valide `GET /health/ready`, abra o web em `:3000`, Scalar em `:8000/docs` e documentação em `:8001`.
