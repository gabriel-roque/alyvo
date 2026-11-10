from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import delete, select

from app.bootstrap.config import get_settings
from app.infrastructure.providers import embedding_provider, object_storage_provider, ocr_provider
from app.modules.knowledge.application.chunking import normalize_extracted_text, structural_chunks
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
        for _ in range(limit):
            with self.factory() as uow:
                event = uow.session.scalar(
                    select(OutboxEvent)
                    .where(OutboxEvent.processed_at.is_(None))
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                if event is None:
                    break
                self.projector.apply(event)
                event.processed_at = datetime.now(timezone.utc)
                processed += 1
        return {"processed": processed}


class ProcessKnowledgeDocument:
    def __init__(self, factory=uow_factory):
        self.factory = factory

    def execute(self, document_id: str) -> dict:
        try:
            with self.factory() as uow:
                document = uow.session.get(KnowledgeDocument, document_id)
                if not document:
                    return {"status": "missing"}
                existing = uow.session.scalars(
                    select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
                ).all()
                if (
                    document.status == DocumentStatus.review_required
                    and existing
                    and all(chunk.embedding for chunk in existing)
                ):
                    return {
                        "status": document.status.value,
                        "chunks": len(existing),
                        "idempotent": True,
                    }
                content = object_storage_provider().get_private(document.storage_key)
                result = ocr_provider().extract(content, document.filename)
                document.content = normalize_extracted_text(result.raw_text)
                if not document.content:
                    raise ValueError("Nenhum texto foi extraído do documento")
                chunks = structural_chunks(document.content)
                if not chunks:
                    raise ValueError("Nenhum chunk foi produzido para o documento")
                embeddings = embedding_provider().embed([chunk.content for chunk in chunks])
                if len(embeddings) != len(chunks) or any(not embedding for embedding in embeddings):
                    raise ValueError("O provedor não retornou embeddings para todos os chunks")
                settings = get_settings()
                uow.session.execute(
                    delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
                )
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
                document.status, document.error = DocumentStatus.review_required, ""
                return {"status": document.status.value, "chunks": len(chunks)}
        except Exception as exc:
            with self.factory() as failure_uow:
                failed = failure_uow.session.get(KnowledgeDocument, document_id)
                if failed:
                    failed.status = DocumentStatus.failed
                    failed.error = f"{type(exc).__name__}: {exc}"[:2000]
            raise
