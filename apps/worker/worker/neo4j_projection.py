from __future__ import annotations

from app.config import get_settings


class Neo4jProjector:
    """Idempotent, tenant-scoped projection. Cypher is constant, never browser-supplied."""

    def __init__(self):
        settings = get_settings()
        self.enabled = settings.app_env != "test"
        self.driver = None
        if self.enabled:
            from neo4j import GraphDatabase

            self.driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def project(self, event_type: str, tenant_id: str, payload: dict) -> None:
        if not self.driver:
            return
        if event_type == "doctor.upserted":
            self._doctor(tenant_id, payload)
        elif event_type == "knowledge.published":
            self._knowledge(tenant_id, payload)
        elif event_type.endswith(".upserted"):
            self._catalog(event_type.split(".")[0], tenant_id, payload)

    def _doctor(self, tenant_id: str, payload: dict) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MERGE (d:Doctor {id: $id, tenant_id: $tenant_id})
                SET d.name = $name, d.crm = $crm, d.specialty_id = $specialty_id,
                    d.unit_id = $unit_id, d.insurer_ids = $insurer_ids
                """,
                tenant_id=tenant_id,
                **payload,
            ).consume()

    def _knowledge(self, tenant_id: str, payload: dict) -> None:
        with self.driver.session() as session:
            session.run(
                """
                MERGE (d:Document {id: $id, tenant_id: $tenant_id})
                SET d.title = $title, d.status = 'published', d.entities = $entities
                """,
                tenant_id=tenant_id,
                **payload,
            ).consume()

    def _catalog(self, kind: str, tenant_id: str, payload: dict) -> None:
        labels = {"specialties": "Specialty", "units": "Unit", "insurers": "Insurer"}
        label = labels.get(kind)
        if not label:
            return
        with self.driver.session() as session:
            session.run(
                f"MERGE (n:{label} {{id: $id, tenant_id: $tenant_id}}) SET n.name = $name",
                id=payload["id"],
                tenant_id=tenant_id,
                name=payload["name"],
            ).consume()

