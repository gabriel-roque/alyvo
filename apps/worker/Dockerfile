FROM python:3.12-slim
WORKDIR /app
COPY apps/api/requirements.txt ./requirements.txt
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONPATH=/app/apps/api:/app/apps/worker
CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=INFO"]

