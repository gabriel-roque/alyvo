FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/apps/api:/app/apps/worker
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY alembic.ini langgraph.json ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS studio
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --extra studio
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser", "--no-reload"]

