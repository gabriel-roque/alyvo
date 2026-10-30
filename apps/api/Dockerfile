FROM python:3.12-slim
WORKDIR /app
COPY apps/api/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
ENV PYTHONPATH=/app/apps/api:/app/apps/worker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

