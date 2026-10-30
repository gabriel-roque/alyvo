from __future__ import annotations

from app.ai.providers import embedding_provider
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
                WITH d
                OPTIONAL MATCH (d)-[old:HAS_SPECIALTY|WORKS_AT|ACCEPTS]->()
                DELETE old
                WITH DISTINCT d
                MATCH (s:Specialty {id: $specialty_id, tenant_id: $tenant_id})
                MATCH (u:Unit {id: $unit_id, tenant_id: $tenant_id})
                MERGE (d)-[:HAS_SPECIALTY]->(s)
                MERGE (d)-[:WORKS_AT]->(u)
                WITH d
                UNWIND $insurer_ids AS insurer_id
                MATCH (i:Insurer {id: insurer_id, tenant_id: $tenant_id})
                MERGE (d)-[:ACCEPTS]->(i)
                """,
                tenant_id=tenant_id,
                **payload,
            ).consume()

    def _knowledge(self, tenant_id: str, payload: dict) -> None:
        chunks = payload.get("chunks", [])
        vectors = embedding_provider().embed(chunks) if chunks else []
        entities = payload.get("entities", [])
        entity_names = [
            entity.get("name", "") if isinstance(entity, dict) else str(entity)
            for entity in entities
        ]
        entity_names = [name for name in entity_names if name]
        with self.driver.session() as session:
            session.run(
                """
                MERGE (d:Document {id: $id, tenant_id: $tenant_id})
                SET d.title = $title, d.status = 'published', d.entities = $entities, d.source = $source
                """,
                tenant_id=tenant_id,
                id=payload["id"],
                title=payload["title"],
                source=payload.get("source", "Base institucional"),
                entities=entity_names,
            ).consume()
            session.run(
                "MATCH (d:Document {id: $id, tenant_id: $tenant_id})-[r:HAS_CHUNK]->(c:Chunk) DETACH DELETE c",
                id=payload["id"],
                tenant_id=tenant_id,
            ).consume()
            for position, (content, vector) in enumerate(zip(chunks, vectors, strict=True)):
                session.run(
                    """
                    MATCH (d:Document {id: $document_id, tenant_id: $tenant_id})
                    CREATE (c:Chunk {id: $chunk_id, tenant_id: $tenant_id, position: $position,
                                     content: $content, embedding: $embedding, status: 'published'})
                    MERGE (d)-[:HAS_CHUNK]->(c)
                    """,
                    document_id=payload["id"],
                    chunk_id=f"{payload['id']}:{position}",
                    tenant_id=tenant_id,
                    position=position,
                    content=content,
                    embedding=vector,
                ).consume()
            for entity in entities:
                entity_type = entity.get("type", "Entity") if isinstance(entity, dict) else "Entity"
                entity_name = entity.get("name", "") if isinstance(entity, dict) else str(entity)
                if not entity_name:
                    continue
                session.run(
                    """
                    MATCH (d:Document {id: $document_id, tenant_id: $tenant_id})
                    MERGE (e:Entity {name: $name, tenant_id: $tenant_id})
                    SET e.entity_type = $entity_type
                    MERGE (d)-[:MENTIONS]->(e)
                    """,
                    document_id=payload["id"],
                    tenant_id=tenant_id,
                    name=entity_name,
                    entity_type=entity_type,
                ).consume()

    def _catalog(self, kind: str, tenant_id: str, payload: dict) -> None:
        labels = {"specialties": "Specialty", "units": "Unit", "insurers": "Insurer", "exams": "Exam", "services": "Service"}
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

