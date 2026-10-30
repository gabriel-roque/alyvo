from __future__ import annotations

from dataclasses import dataclass

from app.ai.providers import embedding_provider
from app.config import get_settings


@dataclass(frozen=True)
class GraphHit:
    content: str
    title: str
    source: str
    score: float


class Neo4jKnowledgeStore:
    def __init__(self) -> None:
        from neo4j import GraphDatabase

        settings = get_settings()
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self.driver.close()

    def relational(self, tenant_id: str) -> list[GraphHit]:
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (d:Doctor {tenant_id: $tenant_id})-[:HAS_SPECIALTY]->(s:Specialty)
                MATCH (d)-[:WORKS_AT]->(u:Unit)
                OPTIONAL MATCH (d)-[:ACCEPTS]->(i:Insurer)
                RETURN d.name AS doctor, d.crm AS crm, s.name AS specialty, u.name AS unit,
                       collect(i.name) AS insurers
                ORDER BY d.name
                """,
                tenant_id=tenant_id,
            )
            return [
                GraphHit(
                    content=(
                        f"{row['doctor']} ({row['crm']}), especialidade {row['specialty']}, "
                        f"atende na {row['unit']}; convênios: {', '.join(row['insurers'])}."
                    ),
                    title="Cadastro aprovado de profissionais",
                    source="Neo4j",
                    score=0.98,
                )
                for row in rows
            ]

    def vector(self, tenant_id: str, question: str, limit: int = 5) -> list[GraphHit]:
        vector = embedding_provider().embed([question])[0]
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (d:Document {tenant_id: $tenant_id, status: 'published'})-[:HAS_CHUNK]->(c:Chunk)
                WHERE c.tenant_id = $tenant_id AND c.status = 'published'
                WITH d, c, vector.similarity.cosine(c.embedding, $embedding) AS score
                WHERE score >= 0.74
                RETURN c.content AS content, d.title AS title, d.source AS source, score
                ORDER BY score DESC
                LIMIT $limit
                """,
                tenant_id=tenant_id,
                embedding=vector,
                limit=limit,
            )
            return [GraphHit(row["content"], row["title"], row["source"], float(row["score"])) for row in rows]

