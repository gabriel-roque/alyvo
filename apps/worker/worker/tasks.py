from datetime import datetime, timezone

from app.ai.providers import embedding_provider, ocr_provider
from app.db import SessionLocal
from app.models import OutboxEvent
from sqlalchemy import select

from worker.celery_app import celery_app
from worker.neo4j_projection import Neo4jProjector


@celery_app.task(name="worker.tasks.project_outbox", autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def project_outbox(limit: int = 100) -> dict:
    processed = 0
    projector = Neo4jProjector()
    try:
        with SessionLocal() as db:
            events = db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for event in events:
                projector.project(event.event_type, event.tenant_id, event.payload)
                event.processed_at = datetime.now(timezone.utc)
                processed += 1
            db.commit()
    finally:
        projector.close()
    return {"processed": processed}


@celery_app.task(name="worker.tasks.extract_document")
def extract_document(content_hex: str, filename: str) -> dict:
    result = ocr_provider().extract(bytes.fromhex(content_hex), filename)
    return {"raw_text": result.raw_text, "fields": result.fields, "confidence": result.confidence}


@celery_app.task(name="worker.tasks.embed_chunks")
def embed_chunks(chunks: list[str]) -> dict:
    vectors = embedding_provider().embed(chunks)
    return {"count": len(vectors), "dimensions": len(vectors[0]) if vectors else 0, "vectors": vectors}

