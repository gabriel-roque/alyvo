"""Local-only LangGraph Studio adapter backed by isolated synthetic data."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import time
from pathlib import Path
from threading import Lock

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.graph import (
    GraphState,
    _build_graph,
    execute_node,
    graph_runtime_context,
    prepare_node,
)
from app.ai.retrieval import local_retrieval_only
from app.db import Base, options_for
from app.models import (
    AvailabilityRule,
    Doctor,
    DocumentStatus,
    Exam,
    Insurer,
    KnowledgeDocument,
    Specialty,
    Tenant,
    Unit,
)

STUDIO_TENANT_ID = "studio-demo"
STUDIO_DATABASE_PATH = (
    Path(__file__).resolve().parents[4] / ".langgraph" / "alyvo-studio-demo.sqlite3"
)
STUDIO_DATABASE_URL = f"sqlite:///{STUDIO_DATABASE_PATH}"

_studio_engine = create_engine(STUDIO_DATABASE_URL, **options_for(STUDIO_DATABASE_URL))
_StudioSession = sessionmaker(bind=_studio_engine, autoflush=False, expire_on_commit=False)
_bootstrap_lock = Lock()
_bootstrapped = False


def _seed_studio_database(db: Session) -> None:
    if db.scalar(select(Tenant.id).where(Tenant.id == STUDIO_TENANT_ID)):
        return

    tenant = Tenant(id=STUDIO_TENANT_ID, name="Alyvo Studio (dados sintéticos)")
    specialty = Specialty(
        tenant_id=STUDIO_TENANT_ID,
        name="Cardiologia demonstrativa",
        description="Especialidade fictícia para estudo local.",
    )
    unit = Unit(
        tenant_id=STUDIO_TENANT_ID,
        name="Unidade Demo",
        address="Rua Exemplo, 100 — endereço fictício",
    )
    insurer = Insurer(tenant_id=STUDIO_TENANT_ID, name="Convênio Demo")
    db.add_all([tenant, specialty, unit, insurer])
    db.flush()

    doctor = Doctor(
        tenant_id=STUDIO_TENANT_ID,
        name="Dra. Demo Local",
        crm="CRM DEMO 0000",
        specialty_id=specialty.id,
        unit_id=unit.id,
        insurer_ids=[insurer.id],
    )
    exam = Exam(
        tenant_id=STUDIO_TENANT_ID,
        name="Exame demonstrativo",
        preparation="Orientação sintética: confirme o preparo com a unidade.",
        unit_ids=[unit.id],
    )
    document = KnowledgeDocument(
        tenant_id=STUDIO_TENANT_ID,
        title="Manual administrativo demonstrativo",
        source="Fixture local do LangGraph Studio",
        content=(
            "A Unidade Demo funciona em dias úteis, das 8h às 18h. "
            "Para o exame demonstrativo, leve um documento fictício e confirme o preparo."
        ),
        status=DocumentStatus.published,
        chunks=[],
    )
    db.add_all([doctor, exam, document])
    db.flush()
    for weekday in range(5):
        db.add(
            AvailabilityRule(
                tenant_id=STUDIO_TENANT_ID,
                doctor_id=doctor.id,
                unit_id=unit.id,
                weekday=weekday,
                starts_at=time(8),
                ends_at=time(18),
                slot_minutes=30,
                active=True,
            )
        )
    db.commit()


def _bootstrap() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    with _bootstrap_lock:
        if _bootstrapped:
            return
        STUDIO_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=_studio_engine)
        with _StudioSession() as db:
            _seed_studio_database(db)
        _bootstrapped = True


@contextmanager
def _studio_runtime():
    _bootstrap()
    with _StudioSession() as db:
        runtime_token = graph_runtime_context.set((db, STUDIO_TENANT_ID, None))
        retrieval_token = local_retrieval_only.set(True)
        try:
            yield
        finally:
            local_retrieval_only.reset(retrieval_token)
            graph_runtime_context.reset(runtime_token)


def studio_prepare_node(state: GraphState) -> dict:
    with _studio_runtime():
        return prepare_node(state)


def studio_execute_node(state: GraphState) -> dict:
    with _studio_runtime():
        return execute_node(state)


# Agent Server provides its own persistence, so this graph intentionally has no
# application checkpointer. Production continues to use graph_app() unchanged.
studio_graph = _build_graph(
    None,
    prepare=studio_prepare_node,
    execute=studio_execute_node,
)
