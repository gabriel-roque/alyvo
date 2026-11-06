from __future__ import annotations

from app.bootstrap.config import get_settings
from app.infrastructure.providers import embedding_provider
from neo4j import GraphDatabase


class Neo4jProjector:
    def __init__(self):
        settings = get_settings()
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.driver.session() as session:
            for label in ("Doctor", "Specialty", "Unit", "Insurer", "Exam", "Document", "Chunk"):
                session.run(
                    f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
                )
            try:
                session.run(
                    "CREATE VECTOR INDEX knowledge_chunk_embedding IF NOT EXISTS FOR (c:Chunk) ON c.embedding OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}"
                )
            except Exception:
                pass
            session.run(
                "CREATE FULLTEXT INDEX knowledge_chunk_text IF NOT EXISTS "
                "FOR (c:Chunk) ON EACH [c.content]"
            )

    def apply(self, event) -> None:
        if event.event_type == "projection.rebuild":
            with self.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            return
        if event.aggregate_type == "doctor":
            self._doctor(event.event_type, event.payload)
        elif event.aggregate_type in {"specialties", "units", "insurers", "exams"}:
            self._catalog(event.aggregate_type, event.event_type, event.payload)
        elif event.event_type == "knowledge.published":
            self._knowledge(event.payload)

    def _doctor(self, event_type: str, payload: dict) -> None:
        with self.driver.session() as session:
            if event_type.endswith("archived"):
                session.run("MATCH (d:Doctor {id: $id}) DETACH DELETE d", id=payload["id"])
                return
            session.run("MERGE (d:Doctor {id: $id}) SET d.name=$name, d.crm=$crm", **payload)
            if payload.get("specialty_id"):
                session.run(
                    "MATCH (d:Doctor {id:$doctor}) MERGE (s:Specialty {id:$target}) MERGE (d)-[:HAS_SPECIALTY]->(s)",
                    doctor=payload["id"],
                    target=payload["specialty_id"],
                )
            if payload.get("unit_id"):
                session.run(
                    "MATCH (d:Doctor {id:$doctor}) MERGE (u:Unit {id:$target}) MERGE (d)-[:WORKS_AT]->(u)",
                    doctor=payload["id"],
                    target=payload["unit_id"],
                )
            for insurer_id in payload.get("insurer_ids", []):
                session.run(
                    "MATCH (d:Doctor {id:$doctor}) MERGE (i:Insurer {id:$target}) MERGE (d)-[:ACCEPTS]->(i)",
                    doctor=payload["id"],
                    target=insurer_id,
                )

    def _catalog(self, kind: str, event_type: str, payload: dict) -> None:
        label = {
            "specialties": "Specialty",
            "units": "Unit",
            "insurers": "Insurer",
            "exams": "Exam",
        }[kind]
        with self.driver.session() as session:
            if event_type.endswith("archived"):
                session.run(f"MATCH (n:{label} {{id:$id}}) DETACH DELETE n", id=payload["id"])
            else:
                session.run(
                    f"MERGE (n:{label} {{id:$id}}) SET n += $payload",
                    id=payload["id"],
                    payload=payload,
                )

    def _knowledge(self, payload: dict) -> None:
        chunks = payload.get("chunks", [])
        embeddings = (
            embedding_provider().embed([item["content"] for item in chunks]) if chunks else []
        )
        with self.driver.session() as session:
            session.run(
                "MERGE (d:Document {id:$id}) SET d.title=$title, d.source=$source",
                id=payload["id"],
                title=payload["title"],
                source=payload.get("source", ""),
            )
            session.run(
                "MATCH (d:Document {id:$id})-[:HAS_CHUNK]->(c:Chunk) DETACH DELETE c",
                id=payload["id"],
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                chunk_id = f"{payload['id']}:{index}"
                session.run(
                    "MATCH (d:Document {id:$document}) MERGE (c:Chunk {id:$id}) SET c.content=$content, c.embedding=$embedding, c.section=$section MERGE (d)-[:HAS_CHUNK]->(c)",
                    document=payload["id"],
                    id=chunk_id,
                    content=chunk["content"],
                    embedding=embedding,
                    section=chunk.get("section", ""),
                )
