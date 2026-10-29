from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Doctor, DocumentStatus, Insurer, KnowledgeDocument, Specialty, Unit


@dataclass(frozen=True)
class RetrievalResult:
    answer_context: list[str]
    citations: list[dict]
    confidence: float
    strategy: str


def retrieve(db: Session, tenant_id: str, question: str) -> RetrievalResult:
    """Tenant-scoped hybrid retrieval; Neo4j adapter mirrors this contract in the worker."""
    lowered = question.casefold()
    relation_terms = {"médico", "medico", "cardiologista", "convênio", "convenio", "unidade", "especialidade"}
    if any(term in lowered for term in relation_terms):
        rows = db.execute(
            select(Doctor, Specialty, Unit)
            .join(Specialty, Doctor.specialty_id == Specialty.id)
            .join(Unit, Doctor.unit_id == Unit.id)
            .where(Doctor.tenant_id == tenant_id, Specialty.tenant_id == tenant_id, Unit.tenant_id == tenant_id)
        ).all()
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

