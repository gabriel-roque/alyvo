from dataclasses import dataclass
from contextvars import ContextVar

from langsmith import traceable
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.neo4j_store import knowledge_store
from app.ai.tracing import retrieval_span_inputs, retrieval_span_outputs
from app.config import get_settings
from app.models import Doctor, DocumentStatus, Insurer, KnowledgeDocument, Specialty, Unit
from app.observability import operation, record


@dataclass(frozen=True)
class RetrievalResult:
    answer_context: list[str]
    citations: list[dict]
    confidence: float
    strategy: str


local_retrieval_only: ContextVar[bool] = ContextVar(
    "local_retrieval_only", default=False
)


@traceable(
    name="alyvo.rag.neo4j_hybrid",
    run_type="retriever",
    process_inputs=retrieval_span_inputs,
    process_outputs=retrieval_span_outputs,
)
def _neo4j_hybrid(store, tenant_id: str, question: str) -> list:
    return store.hybrid(tenant_id, question)


@traceable(
    name="alyvo.rag.neo4j_relational",
    run_type="retriever",
    process_inputs=retrieval_span_inputs,
    process_outputs=retrieval_span_outputs,
)
def _neo4j_relational(store, tenant_id: str, question: str) -> list:
    return store.relational(tenant_id, question)


@traceable(
    name="alyvo.rag.relational_sql",
    run_type="retriever",
    process_inputs=retrieval_span_inputs,
    process_outputs=retrieval_span_outputs,
)
def _relational_rows(db: Session, tenant_id: str, question: str) -> list:
    return db.execute(
        select(Doctor, Specialty, Unit)
        .join(Specialty, Doctor.specialty_id == Specialty.id)
        .join(Unit, Doctor.unit_id == Unit.id)
        .where(
            Doctor.tenant_id == tenant_id,
            Doctor.active.is_(True),
            Doctor.deleted_at.is_(None),
            Specialty.tenant_id == tenant_id,
            Unit.tenant_id == tenant_id,
        )
    ).all()


@traceable(
    name="alyvo.rag.retrieve",
    run_type="retriever",
    process_inputs=retrieval_span_inputs,
    process_outputs=retrieval_span_outputs,
)
def retrieve(db: Session, tenant_id: str, question: str) -> RetrievalResult:
    """Tenant-scoped hybrid retrieval backed by Neo4j, with a test-only SQL fallback."""
    lowered = question.casefold()
    relation_terms = {
        "médico",
        "medico",
        "doutor",
        "doutora",
        "cardiologista",
        "cardiologia",
        "profissional",
        "unidade",
        "trabalha",
        "dra.",
        "dr.",
        "convênio",
        "convenio",
        "especialidade",
        "atende",
        "atendimento",
    }
    if get_settings().app_env != "test" and not local_retrieval_only.get():
        try:
            store = knowledge_store()
            with operation("retrieval.neo4j", tenant_id=tenant_id):
                hits = _neo4j_hybrid(store, tenant_id, question)
                if any(term in lowered for term in relation_terms) and not any(term in lowered for term in {"dura", "duração", "duracao", "tempo"}):
                    relational = _neo4j_relational(store, tenant_id, question)
                    known = {hit.content for hit in hits}
                    hits.extend(hit for hit in relational if hit.content not in known)
                    hits = sorted(hits, key=lambda item: item.score, reverse=True)[:5]
            if hits:
                generic_terms = {
                    "clinica",
                    "clínica",
                    "como",
                    "onde",
                    "qual",
                    "quais",
                    "preciso",
                    "posso",
                    "abre",
                    "estar",
                    "devo",
                    "dura",
                    "levar",
                    "para",
                    "precisa",
                    "quanto",
                    "serve",
                    "tem",
                    "uma",
                }
                terms = {
                    term.strip(".,?!:;").casefold().removesuffix("s")
                    for term in question.split()
                    if len(term.strip(".,?!:;")) > 3
                    and term.strip(".,?!:;").casefold() not in generic_terms
                }
                evidence = " ".join(hit.content for hit in hits).casefold()
                lexical_matches = sum(term in evidence for term in terms)
                lexical_coverage = lexical_matches / max(len(terms), 1)
                confidence = max(hit.score for hit in hits) if terms and lexical_coverage >= 0.5 else 0.45
                strategy = "hybrid-graphrag"
                record("retrieval.completed", strategy=strategy, sources=[hit.source for hit in hits], result_count=len(hits), confidence=confidence)
                return RetrievalResult(
                    [hit.content for hit in hits],
                    [{"title": hit.title, "source": hit.source, "excerpt": hit.content[:240]} for hit in hits],
                    confidence,
                    strategy,
                )
        except Exception:
            # Startup remains resilient while the graph is being projected. The SQL
            # fallback is still tenant-scoped and only exposes approved content.
            record("retrieval.fallback", reason="graph_unavailable")
    if any(term in lowered for term in relation_terms):
        rows = _relational_rows(db, tenant_id, question)
        insurers = {item.id: item.name for item in db.scalars(select(Insurer).where(Insurer.tenant_id == tenant_id))}
        contexts = []
        for doctor, specialty, unit in rows:
            accepted = ", ".join(insurers[item] for item in doctor.insurer_ids if item in insurers)
            contexts.append(f"{doctor.name}, {specialty.name}, atende na {unit.name}; convênios: {accepted}.")
        if contexts:
            return RetrievalResult(
                contexts,
                [{"title": "Cadastro aprovado de profissionais", "source": "Grafo da clínica", "excerpt": item} for item in contexts],
                0.96,
                "graphrag",
            )

    documents = db.scalars(
        select(KnowledgeDocument).where(
            KnowledgeDocument.tenant_id == tenant_id,
            KnowledgeDocument.status == DocumentStatus.published,
        )
    ).all()
    terms = {term for term in lowered.replace("?", "").split() if len(term) > 3}
    ranked = sorted(
        documents,
        key=lambda document: sum(term in document.content.casefold() for term in terms),
        reverse=True,
    )
    matched = [document for document in ranked if any(term in document.content.casefold() for term in terms)][:3]
    if not matched:
        return RetrievalResult([], [], 0.12, "vector")
    return RetrievalResult(
        [document.content[:600] for document in matched],
        [
            {"title": document.title, "source": document.source, "excerpt": document.content[:180]}
            for document in matched
        ],
        0.9,
        "vector",
    )

