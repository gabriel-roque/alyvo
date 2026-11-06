from __future__ import annotations

from app.modules.knowledge.application import ProcessKnowledgeDocument, ProjectOutboxBatch
from app.shared.infrastructure.observability import correlation_id_context, record

from worker.celery_app import celery_app
from worker.neo4j_projection import Neo4jProjector


class WorkerProjector:
    """Dispatches transactional outbox events to the appropriate idempotent projection."""

    def __init__(self) -> None:
        self._neo4j: Neo4jProjector | None = None

    def apply(self, event) -> None:
        if event.event_type == "knowledge.processing.requested":
            ProcessKnowledgeDocument().execute(event.aggregate_id)
            return
        if self._neo4j is None:
            self._neo4j = Neo4jProjector()
        self._neo4j.apply(event)


@celery_app.task(
    name="worker.tasks.project_outbox",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=5,
)
def project_outbox(limit: int = 100, request_id: str = "background") -> dict:
    token = correlation_id_context.set(request_id)
    try:
        result = ProjectOutboxBatch(WorkerProjector()).execute(limit)
        record("outbox.projected", **result)
        return result
    finally:
        correlation_id_context.reset(token)


@celery_app.task(
    name="worker.tasks.process_knowledge_document",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def process_knowledge_document(document_id: str, request_id: str = "background") -> dict:
    token = correlation_id_context.set(request_id)
    try:
        result = ProcessKnowledgeDocument().execute(document_id)
        record("knowledge.processed", document_id=document_id, **result)
        return result
    finally:
        correlation_id_context.reset(token)
