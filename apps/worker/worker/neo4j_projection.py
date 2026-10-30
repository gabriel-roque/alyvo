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
            self.ensure_schema()

    def ensure_schema(self) -> None:
        if not self.driver:
            return
        statements = [
            "CREATE CONSTRAINT tenant_identity IF NOT EXISTS FOR (n:Clinic) REQUIRE (n.id, n.tenant_id) IS UNIQUE",
            "CREATE CONSTRAINT doctor_identity IF NOT EXISTS FOR (n:Doctor) REQUIRE (n.id, n.tenant_id) IS UNIQUE",
            "CREATE CONSTRAINT document_identity IF NOT EXISTS FOR (n:Document) REQUIRE (n.id, n.tenant_id) IS UNIQUE",
            "CREATE CONSTRAINT chunk_identity IF NOT EXISTS FOR (n:Chunk) REQUIRE (n.id, n.tenant_id) IS UNIQUE",
            "CREATE INDEX graph_tenant IF NOT EXISTS FOR (n:Entity) ON (n.tenant_id)",
            "CREATE VECTOR INDEX knowledge_chunk_embedding IF NOT EXISTS FOR (c:Chunk) ON c.embedding OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}",
        ]
        with self.driver.session() as session:
            for statement in statements:
                session.run(statement).consume()

    def close(self) -> None:
        if self.driver:
            self.driver.close()

    def project(self, event_type: str, tenant_id: str, payload: dict) -> None:
        if not self.driver:
            return
        if event_type == "projection.v4.rebuild":
            self._rebuild(tenant_id, payload.get("clinic_name", "Clínica Alyvo"))
            return
        self._clinic(tenant_id, payload.get("clinic_name", "Clínica Alyvo"))
        if event_type.endswith(".deleted"):
            self._delete(event_type.split(".")[0], tenant_id, payload)
        elif event_type == "doctor.upserted":
            self._doctor(tenant_id, payload)
        elif event_type == "knowledge.published":
            self._knowledge(tenant_id, payload)
        elif event_type.endswith(".upserted"):
            self._catalog(event_type.split(".")[0], tenant_id, payload)

    def _clinic(self, tenant_id: str, name: str) -> None:
        with self.driver.session() as session:
            session.run(
                "MERGE (c:Clinic {id: $tenant_id, tenant_id: $tenant_id}) SET c.name = $name",
                tenant_id=tenant_id,
                name=name,
            ).consume()

    def _rebuild(self, tenant_id: str, name: str) -> None:
        with self.driver.session() as session:
            session.run(
                "MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n",
                tenant_id=tenant_id,
            ).consume()
        self._clinic(tenant_id, name)

    def _delete(self, kind: str, tenant_id: str, payload: dict) -> None:
        labels = {
            "doctor": "Doctor",
            "specialties": "Specialty",
            "units": "Unit",
            "insurers": "Insurer",
            "exams": "Exam",
            "services": "Service",
            "knowledge": "Document",
        }
        label = labels.get(kind)
        if not label:
            return
        with self.driver.session() as session:
            session.run(
                f"MATCH (n:{label} {{id: $id, tenant_id: $tenant_id}}) DETACH DELETE n",
                id=payload["id"],
                tenant_id=tenant_id,
            ).consume()

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
                MATCH (clinic:Clinic {id: $tenant_id, tenant_id: $tenant_id})
                MERGE (d)-[:BELONGS_TO]->(clinic)
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
                WITH d
                MATCH (clinic:Clinic {id: $tenant_id, tenant_id: $tenant_id})
                MERGE (clinic)-[:HAS_DOCUMENT]->(d)
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
            session.run(
                """
                MATCH (d:Document {id: $id, tenant_id: $tenant_id})-[mentioned:MENTIONS]->(e:Entity)
                OPTIONAL MATCH (e)-[supported:SUPPORTED_BY]->(d)
                DELETE mentioned, supported
                """,
                id=payload["id"], tenant_id=tenant_id,
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
                entity_id = entity.get("id", f"entity:{entity_type}:{entity_name}") if isinstance(entity, dict) else f"entity:{entity_type}:{entity_name}"
                if not entity_name:
                    continue
                session.run(
                    """
                    MATCH (d:Document {id: $document_id, tenant_id: $tenant_id})
                    MERGE (e:Entity {name: $name, tenant_id: $tenant_id})
                    SET e.id = $entity_id, e.entity_type = $entity_type
                    MERGE (d)-[:MENTIONS]->(e)
                    MERGE (e)-[:SUPPORTED_BY]->(d)
                    """,
                    document_id=payload["id"],
                    tenant_id=tenant_id,
                    name=entity_name,
                    entity_id=entity_id,
                    entity_type=entity_type,
                ).consume()

    def _catalog(self, kind: str, tenant_id: str, payload: dict) -> None:
        labels = {"specialties": "Specialty", "units": "Unit", "insurers": "Insurer", "exams": "Exam", "services": "Service"}
        label = labels.get(kind)
        if not label:
            return
        with self.driver.session() as session:
            session.run(
                f"""
                MERGE (n:{label} {{id: $id, tenant_id: $tenant_id}})
                SET n += $properties
                WITH n
                MATCH (clinic:Clinic {{id: $tenant_id, tenant_id: $tenant_id}})
                MERGE (n)-[:BELONGS_TO]->(clinic)
                """,
                id=payload["id"],
                tenant_id=tenant_id,
                properties={key: value for key, value in payload.items() if key != "id" and not key.startswith("_")},
            ).consume()
            if kind == "exams":
                session.run(
                    """
                    MATCH (e:Exam {id: $id, tenant_id: $tenant_id})
                    OPTIONAL MATCH (e)<-[old:PERFORMS]-(:Unit) DELETE old
                    WITH e
                    UNWIND $unit_ids AS unit_id
                    MATCH (u:Unit {id: unit_id, tenant_id: $tenant_id})
                    MERGE (u)-[:PERFORMS]->(e)
                    """,
                    id=payload["id"], tenant_id=tenant_id, unit_ids=payload.get("unit_ids", []),
                ).consume()
            elif kind == "services":
                session.run(
                    """
                    MATCH (service:Service {id: $id, tenant_id: $tenant_id})
                    MATCH (clinic:Clinic {id: $tenant_id, tenant_id: $tenant_id})
                    MERGE (clinic)-[:OFFERS]->(service)
                    WITH service
                    OPTIONAL MATCH (service)-[old:HAS_SPECIALTY]->(:Specialty) DELETE old
                    WITH service
                    OPTIONAL MATCH (specialty:Specialty {id: $specialty_id, tenant_id: $tenant_id})
                    FOREACH (_ IN CASE WHEN specialty IS NULL THEN [] ELSE [1] END |
                        MERGE (service)-[:HAS_SPECIALTY]->(specialty))
                    """,
                    id=payload["id"], tenant_id=tenant_id, specialty_id=payload.get("specialty_id"),
                ).consume()

