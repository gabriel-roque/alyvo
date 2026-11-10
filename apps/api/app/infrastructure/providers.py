from __future__ import annotations

import hashlib
import io
import math
import re
import tempfile
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.bootstrap.config import Settings, get_settings

if TYPE_CHECKING:
    from app.agent.routing import RouteDecision


@dataclass(frozen=True)
class OcrResult:
    raw_text: str
    fields: dict[str, str]
    confidence: dict[str, float]


@dataclass(frozen=True)
class KnowledgeHit:
    chunk_id: str
    content: str
    title: str
    source: str
    score: float


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OcrProvider(ABC):
    @abstractmethod
    def extract(self, content: bytes, filename: str) -> OcrResult: ...


class ObjectStorageProvider(ABC):
    @abstractmethod
    def put_private(self, key: str, content: bytes, content_type: str) -> str: ...

    @abstractmethod
    def get_private(self, key: str) -> bytes: ...

    @abstractmethod
    def delete_private(self, key: str) -> None: ...


class DeterministicEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: list[str]) -> list[list[float]]:
        rows = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            values = [((digest[index % len(digest)] / 255) * 2) - 1 for index in range(1024)]
            norm = math.sqrt(sum(value * value for value in values)) or 1
            rows.append([value / norm for value in values])
        return rows


class BgeM3EmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(settings.embedding_model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True).tolist()


class DeterministicOcrProvider(OcrProvider):
    def extract(self, content: bytes, filename: str) -> OcrResult:
        text = content.decode(errors="ignore") or Path(filename).stem.replace("-", " ")
        return OcrResult(text, {}, {"document": 1.0})


class PaddleOcrProvider(OcrProvider):
    def __init__(self):
        self._ocr: Any | None = None

    def _engine(self) -> Any:
        if self._ocr is not None:
            return self._ocr

        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(
            use_angle_cls=True,
            lang="pt",
            show_log=False,
        )
        return self._ocr

    def extract(self, content: bytes, filename: str) -> OcrResult:
        suffix = Path(filename).suffix.casefold() or ".bin"
        if suffix in {".txt", ".md", ".csv"}:
            text = content.decode("utf-8", errors="replace").strip()
            return OcrResult(text, {}, {"document": 1.0 if text else 0.0})

        if suffix == ".pdf":
            from pypdf import PdfReader

            pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages]
            text = "\f".join(page.strip() for page in pages).strip()
            if text:
                return OcrResult(text, {}, {"document": 0.95})

        with tempfile.NamedTemporaryFile(suffix=suffix) as file:
            file.write(content)
            file.flush()
            result = self._engine().ocr(file.name, cls=True)
        lines: list[str] = []
        scores: list[float] = []
        for page in result or []:
            for line in page or []:
                if not isinstance(line, (list, tuple)) or len(line) < 2:
                    continue
                recognized = line[1]
                if isinstance(recognized, (list, tuple)) and recognized:
                    lines.append(str(recognized[0]))
                    if len(recognized) > 1:
                        scores.append(float(recognized[1]))
        confidence = sum(scores) / len(scores) if scores else (0.8 if lines else 0.0)
        return OcrResult("\n".join(lines), {}, {"document": confidence})


class LocalObjectStorage(ObjectStorageProvider):
    def __init__(self):
        self._objects: dict[str, bytes] = {}

    def put_private(self, key: str, content: bytes, content_type: str) -> str:
        self._objects[key] = content
        return key

    def get_private(self, key: str) -> bytes:
        return self._objects[key]

    def delete_private(self, key: str) -> None:
        self._objects.pop(key, None)


class MinioObjectStorage(ObjectStorageProvider):
    def __init__(self, settings: Settings):
        import boto3

        self.bucket = settings.minio_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"{'https' if settings.minio_secure else 'http'}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
        )
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def put_private(self, key: str, content: bytes, content_type: str) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)
        return key

    def get_private(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete_private(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


class LlmRoutingClassifier:
    """Probabilistic last resort behind the deterministic routing rules."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def __call__(self, message: str) -> RouteDecision | None:
        from app.agent.routing import RouteDecision

        model = self._model()
        if model is None:
            return None
        prompt = (
            "Classifique a mensagem administrativa usando apenas o schema solicitado. "
            "Nunca escolha ação clínica; use clinical_safety para diagnóstico ou emergência.\n"
            f"Mensagem: {message}"
        )
        try:
            return model.with_structured_output(RouteDecision).invoke(prompt)
        except Exception:
            return None

    def _model(self):
        settings = self.settings
        if (
            settings.llm_primary_provider == "openrouter"
            and settings.allow_external_providers
            and settings.openrouter_api_key
        ):
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
                model=settings.openrouter_model,
                timeout=settings.openrouter_timeout_seconds,
                max_retries=settings.openrouter_max_retries,
                temperature=0,
            )
        if settings.llm_fallback_provider == "ollama" or settings.llm_primary_provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
                temperature=0,
                keep_alive=settings.ollama_keep_alive,
            )
        return None


@lru_cache
def embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    return (
        DeterministicEmbeddingProvider()
        if settings.embedding_provider == "mock"
        else BgeM3EmbeddingProvider(settings)
    )


@lru_cache
def ocr_provider() -> OcrProvider:
    return (
        DeterministicOcrProvider() if get_settings().ocr_provider == "mock" else PaddleOcrProvider()
    )


@lru_cache
def object_storage_provider() -> ObjectStorageProvider:
    settings = get_settings()
    return LocalObjectStorage() if settings.app_env == "test" else MinioObjectStorage(settings)


@lru_cache
def routing_classifier():
    settings = get_settings()
    if settings.app_env in {"test", "studio"} or not settings.llm_routing_enabled:
        return None
    return LlmRoutingClassifier(settings)


HYBRID_KNOWLEDGE_QUERY = """
CALL () {
  CALL db.index.fulltext.queryNodes('knowledge_chunk_text', $question, {limit: 30})
  YIELD node, score
  WITH collect({node: node, score: score}) AS rows
  UNWIND range(0, size(rows) - 1) AS rank
  RETURN rows[rank].node AS chunk,
         1.0 / (60 + rank + 1) AS rrf,
         rows[rank].score AS lexical_score,
         0.0 AS vector_score
  UNION ALL
  CALL db.index.vector.queryNodes('knowledge_chunk_embedding', 30, $embedding)
  YIELD node, score
  WITH collect({node: node, score: score}) AS rows
  UNWIND range(0, size(rows) - 1) AS rank
  RETURN rows[rank].node AS chunk,
         1.0 / (60 + rank + 1) AS rrf,
         0.0 AS lexical_score,
         rows[rank].score AS vector_score
}
MATCH (document:Document)-[:HAS_CHUNK]->(chunk)
WITH document, chunk, sum(rrf) AS rrf_score,
     max(lexical_score) AS lexical_score,
     max(vector_score) AS vector_score
WHERE lexical_score > 0 OR vector_score >= $minimum_vector_score
RETURN chunk.id AS chunk_id, chunk.content AS content,
       document.title AS title, document.source AS source,
       lexical_score, vector_score, rrf_score
ORDER BY rrf_score DESC LIMIT 30
"""


def hybrid_knowledge_search(question: str, limit: int = 5) -> list[KnowledgeHit]:
    """Run full-text/vector RRF in Neo4j; callers own the SQL fallback."""
    from neo4j import GraphDatabase

    settings = get_settings()
    embedding = embedding_provider().embed([question])[0]
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=2,
    )
    try:
        with driver.session() as session:
            rows = session.run(
                HYBRID_KNOWLEDGE_QUERY,
                question=question,
                embedding=embedding,
                minimum_vector_score=settings.knowledge_vector_min_score,
                limit=limit,
            )
            ranked: list[tuple[float, float, KnowledgeHit]] = []
            for row in rows:
                vector_score = float(row["vector_score"] or 0)
                lexical_strength = _lexical_strength(
                    question,
                    f"{row['title']} {row['content']}",
                )
                lexical_score = 0.86 * lexical_strength if lexical_strength >= 0.5 else 0
                semantic_score = (
                    vector_score if vector_score >= settings.knowledge_vector_min_score else 0
                )
                relevance = max(lexical_score, semantic_score)
                if relevance <= 0:
                    continue
                ranked.append(
                    (
                        relevance,
                        float(row["rrf_score"]),
                        KnowledgeHit(
                            chunk_id=row["chunk_id"],
                            content=row["content"],
                            title=row["title"],
                            source=row["source"] or "Base institucional",
                            score=relevance,
                        ),
                    )
                )
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [item[2] for item in ranked[:limit]]
    finally:
        driver.close()


def _lexical_strength(question: str, content: str) -> float:
    question_terms = _search_terms(question)
    if not question_terms:
        return 0
    content_terms = _search_terms(content)
    matches = sum(
        any(_same_term(term, candidate) for candidate in content_terms) for term in question_terms
    )
    return matches / len(question_terms)


def _same_term(left: str, right: str) -> bool:
    if left == right:
        return True
    return min(len(left), len(right)) >= 5 and (
        left.startswith(right[:5]) or right.startswith(left[:5])
    )


def _search_terms(value: str) -> set[str]:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    stop_words = {
        "aos",
        "como",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "em",
        "nos",
        "para",
        "por",
        "qual",
        "quais",
        "que",
        "uma",
        "voces",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]+", plain)
        if len(token) >= 3 and token not in stop_words
    }
