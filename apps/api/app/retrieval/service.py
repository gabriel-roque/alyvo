from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum

from langsmith import traceable
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.conversation import normalized_text
from app.ai.tracing import retrieval_span_inputs, retrieval_span_outputs
from app.config import get_settings
from app.infrastructure.neo4j import GraphHit, knowledge_store
from app.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from app.observability import operation, record
from app.retrieval.reranker import local_reranker


class AnswerabilityStatus(StrEnum):
    SUPPORTED = "supported"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class Evidence:
    id: str
    content: str
    title: str
    source: str
    fusion_score: float
    vector_score: float | None = None
    lexical_score: float | None = None
    reranker_score: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    answer_context: list[str]
    citations: list[dict[str, str]]
    confidence: float
    strategy: str
    answerability: AnswerabilityStatus
    evidence: tuple[Evidence, ...] = ()


local_retrieval_only: ContextVar[bool] = ContextVar("local_retrieval_only", default=False)

STOP_WORDS = {
    "a",
    "as",
    "com",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "fica",
    "o",
    "os",
    "para",
    "por",
    "qual",
    "quais",
    "que",
    "sao",
    "uma",
    "um",
    "voce",
    "voces",
    "pra",
    "pro",
}


def _terms(value: str) -> set[str]:
    return {
        token
        for token in normalized_text(value).split()
        if len(token) >= 3 and token not in STOP_WORDS
    }


def _answerability(question: str, evidence: list[Evidence]) -> tuple[AnswerabilityStatus, float]:
    if not evidence:
        return AnswerabilityStatus.INSUFFICIENT, 0.12
    query_terms = _terms(question)
    evidence_terms = _terms(" ".join(item.content for item in evidence))
    lexical_coverage = len(query_terms & evidence_terms) / max(len(query_terms), 1)
    strongest_vector = max(
        (item.vector_score or 0.0 for item in evidence),
        default=0.0,
    )
    if lexical_coverage >= 0.35 or strongest_vector >= 0.68:
        # This is an answerability indicator calibrated by evidence coverage; it
        # intentionally does not expose or rescale the RRF score.
        confidence = min(0.97, 0.72 + lexical_coverage * 0.2 + strongest_vector * 0.05)
        return AnswerabilityStatus.SUPPORTED, confidence
    return AnswerabilityStatus.INSUFFICIENT, min(0.49, 0.2 + lexical_coverage * 0.5)


def _to_evidence(hits: list[GraphHit]) -> list[Evidence]:
    return [
        Evidence(
            id=f"evidence-{index}",
            content=hit.content,
            title=hit.title,
            source=hit.source,
            fusion_score=hit.score,
            vector_score=hit.vector_score,
            lexical_score=hit.lexical_score,
        )
        for index, hit in enumerate(hits, start=1)
    ]


def _rerank(question: str, evidence: list[Evidence]) -> list[Evidence]:
    if not get_settings().reranker_enabled or len(evidence) < 2:
        return evidence[:5]
    ranked = local_reranker().rank(question, [item.content for item in evidence[:20]])
    return [
        Evidence(
            **{
                **evidence[index].__dict__,
                "reranker_score": score,
            }
        )
        for index, score in ranked[:5]
    ]


def _sql_candidates(db: Session, tenant_id: str, question: str) -> list[Evidence]:
    query_terms = _terms(question)
    rows = db.execute(
        select(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeChunk.tenant_id == tenant_id,
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.status == DocumentStatus.published,
        )
    ).all()
    ranked: list[tuple[float, KnowledgeChunk, KnowledgeDocument]] = []
    for chunk, document in rows:
        coverage = len(query_terms & _terms(chunk.content)) / max(len(query_terms), 1)
        if coverage:
            ranked.append((coverage, chunk, document))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked:
        return [
            Evidence(
                id=chunk.id,
                content=chunk.content,
                title=document.title,
                source=document.source,
                fusion_score=coverage,
                lexical_score=coverage,
            )
            for coverage, chunk, document in ranked[:20]
        ]

    # Compatibility for approved text records created before chunk persistence.
    documents = db.scalars(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.status == DocumentStatus.published,
        )
    ).all()
    legacy = []
    for document in documents:
        coverage = len(query_terms & _terms(document.content)) / max(len(query_terms), 1)
        if coverage:
            legacy.append((coverage, document))
    legacy.sort(key=lambda item: item[0], reverse=True)
    return [
        Evidence(
            id=f"document-{document.id}",
            content=document.content[:1200],
            title=document.title,
            source=document.source,
            fusion_score=coverage,
            lexical_score=coverage,
        )
        for coverage, document in legacy[:5]
    ]


@traceable(
    name="alyvo.rag.retrieve",
    run_type="retriever",
    process_inputs=retrieval_span_inputs,
    process_outputs=retrieval_span_outputs,
)
def retrieve(db: Session, tenant_id: str, question: str) -> RetrievalResult:
    evidence: list[Evidence] = []
    strategy = "hybrid"
    if get_settings().app_env != "test" and not local_retrieval_only.get():
        try:
            with operation("retrieval.neo4j", tenant_id=tenant_id):
                store = knowledge_store()
                hits = store.hybrid(tenant_id, question, limit=20)
                relation_terms = {
                    "medico",
                    "médico",
                    "doutor",
                    "doutora",
                    "profissional",
                    "unidade",
                    "trabalha",
                    "atende",
                    "especialidade",
                    "convenio",
                    "convênio",
                }
                if _terms(question) & relation_terms:
                    known = {hit.content for hit in hits}
                    hits.extend(
                        hit
                        for hit in store.relational(tenant_id, question)
                        if hit.content not in known
                    )
                evidence = _to_evidence(hits[:20])
        except Exception as exc:
            record("retrieval.fallback", reason=type(exc).__name__)
            strategy = "lexical-sql-fallback"
    if not evidence:
        evidence = _sql_candidates(db, tenant_id, question)
        strategy = "lexical-sql-fallback"

    selected = _rerank(question, evidence)
    status, confidence = _answerability(question, selected)
    record(
        "retrieval.completed",
        strategy=strategy,
        result_count=len(selected),
        answerability=status.value,
        confidence=confidence,
        fusion_scores=[round(item.fusion_score, 6) for item in selected],
        vector_scores=[item.vector_score for item in selected],
        lexical_scores=[item.lexical_score for item in selected],
        reranker_scores=[item.reranker_score for item in selected],
        index_version=get_settings().knowledge_index_version,
    )
    if status != AnswerabilityStatus.SUPPORTED:
        return RetrievalResult([], [], confidence, strategy, status, tuple(selected))
    return RetrievalResult(
        [item.content for item in selected],
        [
            {
                "title": item.title,
                "source": item.source,
                "excerpt": item.content[:240],
            }
            for item in selected
        ],
        confidence,
        strategy,
        status,
        tuple(selected),
    )
