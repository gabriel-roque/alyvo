FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/apps/api:/app/apps/worker
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra ocr --no-install-project
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra ocr
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]

