FROM python:3.11-slim
WORKDIR /app
COPY apps/api/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY apps/worker/requirements.txt ./worker-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r worker-requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0t64 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
ENV PYTHONPATH=/app/apps/api:/app/apps/worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]

