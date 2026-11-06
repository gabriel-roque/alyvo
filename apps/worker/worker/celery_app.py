from app.bootstrap.config import get_settings
from celery import Celery

settings = get_settings()
celery_app = Celery(
    "alyvo",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "project-outbox": {"task": "worker.tasks.project_outbox", "schedule": 5.0},
    },
)
