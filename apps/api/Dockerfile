FROM python:3.12-slim AS api-base
WORKDIR /app
COPY apps/api/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
ENV PYTHONPATH=/app/apps/api:/app/apps/worker

FROM api-base AS studio
COPY pyproject.toml langgraph.json ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -e '.[studio]'
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser", "--no-reload"]

FROM api-base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

