from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select

from app.bootstrap.config import get_settings
from app.infrastructure.providers import embedding_provider, object_storage_provider, ocr_provider
from app.modules.knowledge.application.chunking import structural_chunks
from app.shared.infrastructure.models import (
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    OutboxEvent,
)
from app.shared.infrastructure.uow import uow_factory


class ProjectionPort(Protocol):
    def apply(self, event: OutboxEvent) -> None: ...


class ProjectOutboxBatch:
    def __init__(self, projector: ProjectionPort, factory=uow_factory):
        self.projector, self.factory = projector, factory

    def execute(self, limit: int = 100) -> dict:
        processed = 0
        with self.factory() as uow:
            events = uow.session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.processed_at.is_(None))
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            for event in events:
                self.projector.apply(event)
                event.processed_at = datetime.now(timezone.utc)
                processed += 1
        return {"processed": processed}


class ProcessKnowledgeDocument:
    def __init__(self, factory=uow_factory):
        self.factory = factory

    def execute(self, document_id: str) -> dict:
        with self.factory() as uow:
            document = uow.session.get(KnowledgeDocument, document_id)
            if not document:
                return {"status": "missing"}
            try:
                content = object_storage_provider().get_private(document.storage_key)
                result = ocr_provider().extract(content, document.filename)
                document.content = result.raw_text
                chunks = structural_chunks(result.raw_text)
                embeddings = embedding_provider().embed([chunk.content for chunk in chunks])
                settings = get_settings()
                for position, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                    uow.session.add(
                        KnowledgeChunk(
                            document_id=document.id,
                            position=position,
                            content=chunk.content,
                            embedding=embedding,
                            content_hash=chunk.content_hash,
                            section=chunk.section,
                            page=chunk.page,
                            parent_id=chunk.parent_id,
                            parser_version=settings.chunk_parser_version,
                            embedding_model=settings.embedding_model,
                            index_version=settings.knowledge_index_version,
                        )
                    )
                document.status = DocumentStatus.review_required
                return {"status": document.status.value, "chunks": len(chunks)}
            except Exception as exc:
                document.status, document.error = DocumentStatus.failed, type(exc).__name__
                raise
