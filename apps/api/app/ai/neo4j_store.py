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

    def relational(self, tenant_id: str, question: str = "") -> list[GraphHit]:
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
                CALL db.index.vector.queryNodes('knowledge_chunk_embedding', $candidate_limit, $embedding)
                YIELD node AS c, score
                MATCH (d:Document {tenant_id: $tenant_id, status: 'published'})-[:HAS_CHUNK]->(c)
                WHERE c.tenant_id = $tenant_id AND c.status = 'published' AND score >= 0.55
                RETURN c.content AS content, d.title AS title, d.source AS source, score
                ORDER BY score DESC
                LIMIT $limit
                """,
                tenant_id=tenant_id,
                embedding=vector,
                limit=limit,
                candidate_limit=max(limit * 10, 50),
            )
            return [GraphHit(row["content"], row["title"], row["source"], float(row["score"])) for row in rows]

    def hybrid(self, tenant_id: str, question: str, limit: int = 5) -> list[GraphHit]:
        """Vector seeds plus graph expansion, followed by deterministic reranking."""
        vector = embedding_provider().embed([question])[0]
        terms = {term.strip(".,?!:;").casefold() for term in question.split() if len(term) > 3}
        with self.driver.session() as session:
            rows = list(session.run(
                """
                CALL db.index.vector.queryNodes('knowledge_chunk_embedding', 50, $embedding)
                YIELD node AS chunk, score
                MATCH (document:Document {tenant_id: $tenant_id, status: 'published'})-[:HAS_CHUNK]->(chunk)
                WHERE chunk.tenant_id = $tenant_id AND chunk.status = 'published'
                OPTIONAL MATCH (document)-[:MENTIONS]->(entity:Entity)
                OPTIONAL MATCH (entity)-[:SUPPORTED_BY]->(support:Document)-[:HAS_CHUNK]->(expanded:Chunk)
                WHERE support.tenant_id = $tenant_id AND expanded.tenant_id = $tenant_id
                RETURN chunk.content AS content, document.title AS title, document.source AS source,
                       score, collect(DISTINCT entity.name) AS entities,
                       collect(DISTINCT expanded.content)[..3] AS expanded
                ORDER BY score DESC
                LIMIT 12
                """,
                tenant_id=tenant_id,
                embedding=vector,
            ))
        hits: list[GraphHit] = []
        seen: set[str] = set()
        for row in rows:
            candidates = [(row["content"], float(row["score"]))]
            candidates.extend((content, max(float(row["score"]) - 0.08, 0.0)) for content in row["expanded"] if content)
            for content, base_score in candidates:
                if content in seen:
                    continue
                seen.add(content)
                lexical = sum(term in content.casefold() for term in terms) / max(len(terms), 1)
                entity_match = sum(term in " ".join(row["entities"]).casefold() for term in terms)
                score = min(base_score * 0.75 + lexical * 0.2 + min(entity_match, 1) * 0.05, 1.0)
                hits.append(GraphHit(content, row["title"], row["source"], score))
        return sorted(hits, key=lambda item: item.score, reverse=True)[:limit]

