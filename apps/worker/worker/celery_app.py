from app.config import get_settings
from celery import Celery

settings = get_settings()
celery_app = Celery("alyvo", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "project-outbox": {"task": "worker.tasks.project_outbox", "schedule": 5.0},
        "enforce-document-retention": {
            "task": "worker.tasks.enforce_document_retention",
            "schedule": 86400.0,
        },
    },
)
celery_app.autodiscover_tasks(["worker"])

