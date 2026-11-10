from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.bootstrap.config import get_settings
from app.infrastructure.providers import hybrid_knowledge_search
from app.modules.knowledge.application.chunking import structural_chunks
from app.modules.knowledge.domain.models import Answerability, Evidence, RetrievalResult
from app.shared.application import NotFoundError, ValidationError
from app.shared.infrastructure.models import (
    AuditEvent,
    DocumentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    OutboxEvent,
)
from app.shared.infrastructure.uow import uow_factory


@dataclass(frozen=True)
class KnowledgeUpload:
    id: str
    title: str
    filename: str
    content_type: str
    storage_key: str


class KnowledgeService:
    def __init__(self, factory=uow_factory):
        self._factory = factory

    def create_text(self, title: str, content: str, actor_id: str) -> dict:
        with self._factory() as uow:
            item = KnowledgeDocument(
                title=title, content=content, status=DocumentStatus.review_required
            )
            uow.session.add(item)
            uow.flush()
            self._audit(uow.session, actor_id, "knowledge.created", item.id)
            return self._view(item)

    def create_uploads(self, uploads: list[KnowledgeUpload], actor_id: str) -> list[dict]:
        with self._factory() as uow:
            created = []
            for upload in uploads:
                item = KnowledgeDocument(
                    id=upload.id,
                    title=upload.title,
                    filename=upload.filename,
                    storage_key=upload.storage_key,
                    content_type=upload.content_type,
                    status=DocumentStatus.processing,
                )
                uow.session.add(item)
                uow.flush()
                self._audit(uow.session, actor_id, "knowledge.uploaded", item.id)
                uow.session.add(
                    OutboxEvent(
                        aggregate_type="knowledge_document",
                        aggregate_id=item.id,
                        event_type="knowledge.processing.requested",
                        payload={"id": item.id},
                    )
                )
                created.append(self._view(item))
            return created

    def list_documents(self) -> dict:
        with self._factory() as uow:
            rows = uow.session.scalars(
                select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
            ).all()
            items = [self._view(item, self._sync_status(uow.session, item)) for item in rows]
            return {"items": items, "total": len(items), "page": 1, "page_size": len(items)}

    def publish(self, document_id: str, entities: list[dict], actor_id: str) -> dict:
        with self._factory() as uow:
            item = uow.session.get(KnowledgeDocument, document_id)
            if not item:
                raise NotFoundError("Documento não encontrado")
            if item.status != DocumentStatus.review_required:
                raise ValidationError("Documento não pode ser publicado neste estado")
            item.status, item.entities = DocumentStatus.published, entities
            chunks = uow.session.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == item.id)
                .order_by(KnowledgeChunk.position)
            ).all()
            if not chunks:
                chunks = self._persist_chunks(uow.session, item)
            uow.session.add(
                OutboxEvent(
                    aggregate_type="knowledge_document",
                    aggregate_id=item.id,
                    event_type="knowledge.published",
                    payload={
                        "id": item.id,
                        "title": item.title,
                        "source": item.source,
                        "entities": entities,
                        "chunks": [self._chunk_view(chunk) for chunk in chunks],
                    },
                )
            )
            self._audit(uow.session, actor_id, "knowledge.published", item.id)
            return self._view(item, "pending")

    def reject(self, document_id: str, actor_id: str) -> dict:
        with self._factory() as uow:
            item = uow.session.get(KnowledgeDocument, document_id)
            if not item:
                raise NotFoundError("Documento não encontrado")
            item.status = DocumentStatus.rejected
            self._audit(uow.session, actor_id, "knowledge.rejected", item.id)
            return self._view(item)

    def retrieve(self, question: str) -> RetrievalResult:
        if get_settings().app_env not in {"test", "studio"}:
            try:
                hits = hybrid_knowledge_search(question)
                if hits:
                    minimum_relevance = max(hit.score for hit in hits) - 0.04
                    hits = [hit for hit in hits if hit.score >= minimum_relevance]
                    evidence = tuple(
                        Evidence(hit.chunk_id, hit.content, hit.title, hit.source, hit.score)
                        for hit in hits
                    )
                    return RetrievalResult(
                        evidence,
                        min(0.97, max(hit.score for hit in hits)),
                        "neo4j-rrf",
                        Answerability.SUPPORTED,
                    )
            except Exception:
                pass
        terms = self._terms(question)
        with self._factory() as uow:
            rows = uow.session.execute(
                select(KnowledgeChunk, KnowledgeDocument)
                .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                .where(KnowledgeDocument.status == DocumentStatus.published)
            ).all()
            ranked = []
            for chunk, document in rows:
                coverage = len(terms & self._terms(chunk.content)) / max(len(terms), 1)
                if coverage:
                    ranked.append(
                        Evidence(chunk.id, chunk.content, document.title, document.source, coverage)
                    )
            ranked.sort(key=lambda item: item.score, reverse=True)
            selected = tuple(ranked[:5])
            confidence = min(0.97, 0.72 + (selected[0].score * 0.2)) if selected else 0.12
            answerability = (
                Answerability.SUPPORTED
                if selected and selected[0].score >= 0.35
                else Answerability.INSUFFICIENT
            )
            return RetrievalResult(selected, confidence, "lexical-sql", answerability)

    @staticmethod
    def _persist_chunks(session, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        settings = get_settings()
        rows = []
        for position, chunk in enumerate(structural_chunks(document.content)):
            item = KnowledgeChunk(
                document_id=document.id,
                position=position,
                content=chunk.content,
                content_hash=chunk.content_hash,
                section=chunk.section,
                page=chunk.page,
                parent_id=chunk.parent_id,
                parser_version=settings.chunk_parser_version,
                embedding_model=settings.embedding_model,
                index_version=settings.knowledge_index_version,
            )
            session.add(item)
            rows.append(item)
        return rows

    @staticmethod
    def _terms(value: str) -> set[str]:
        stop = {"para", "com", "uma", "que", "qual", "quais", "dos", "das", "por", "voces"}
        normalized = "".join(
            character.lower() if character.isalnum() else " " for character in value
        )
        return {token for token in normalized.split() if len(token) >= 3 and token not in stop}

    @staticmethod
    def _view(item: KnowledgeDocument, sync_status: str = "not_applicable") -> dict:
        return {
            "id": item.id,
            "title": item.title,
            "status": item.status.value,
            "source": item.source,
            "entities": item.entities,
            "preview": item.content[:800],
            "filename": item.filename,
            "error": item.error,
            "sync_status": sync_status,
        }

    @staticmethod
    def _sync_status(session, item: KnowledgeDocument) -> str:
        if item.status != DocumentStatus.published:
            return "not_applicable"
        event = session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_id == item.id,
                OutboxEvent.event_type == "knowledge.published",
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(1)
        )
        return "synced" if event and event.processed_at else "pending"

    @staticmethod
    def _chunk_view(item: KnowledgeChunk) -> dict:
        return {
            "content": item.content,
            "content_hash": item.content_hash,
            "section": item.section,
            "page": item.page,
            "parent_id": item.parent_id,
            "parser_version": item.parser_version,
            "embedding_model": item.embedding_model,
            "index_version": item.index_version,
        }

    @staticmethod
    def _audit(session, actor_id: str, action: str, resource_id: str) -> None:
        session.add(
            AuditEvent(
                actor_id=actor_id,
                action=action,
                resource_type="knowledge_document",
                resource_id=resource_id,
            )
        )
