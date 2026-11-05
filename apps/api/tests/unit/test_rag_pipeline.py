from __future__ import annotations

import pytest
from app.agent.routing import Action, Domain, RouteDecision, Topic
from app.ai.neo4j_store import GraphHit, Neo4jKnowledgeStore
from app.retrieval.chunking import structural_chunks
from app.retrieval.service import AnswerabilityStatus, Evidence, _answerability
from app.tools import validate_tool_arguments
from pydantic import ValidationError


def test_rrf_keeps_raw_fusion_scores_without_fake_confidence(monkeypatch):
    store = Neo4jKnowledgeStore.__new__(Neo4jKnowledgeStore)
    dense = [GraphHit("A", "Doc", "Base", 0.91), GraphHit("B", "Doc", "Base", 0.8)]
    lexical = [GraphHit("B", "Doc", "Base", 12.0), GraphHit("A", "Doc", "Base", 8.0)]
    monkeypatch.setattr(store, "vector", lambda *_args, **_kwargs: dense)
    monkeypatch.setattr(store, "fulltext", lambda *_args, **_kwargs: lexical)

    hits = store.hybrid("tenant", "pergunta")

    assert {hit.content for hit in hits} == {"A", "B"}
    assert max(hit.score for hit in hits) < 0.1
    assert all(hit.vector_score is not None for hit in hits)
    assert all(hit.lexical_score is not None for hit in hits)


def test_answerability_does_not_use_rrf_as_probability():
    evidence = [
        Evidence(
            id="e1",
            content="O retorno de consulta particular ocorre em até 30 dias.",
            title="Política",
            source="Base aprovada",
            fusion_score=0.02,
            vector_score=0.82,
        )
    ]
    status, confidence = _answerability("prazo retorno consulta particular", evidence)
    assert status == AnswerabilityStatus.SUPPORTED
    assert confidence >= 0.7
    assert confidence != evidence[0].fusion_score


def test_structural_chunking_retains_heading_page_and_parent():
    text = (
        "POLÍTICA DE RETORNO\n"
        + "consulta retorno particular " * 400
        + "\fEXAMES\nHemograma em 1 dia"
    )
    chunks = structural_chunks(text)
    assert len(chunks) > 2
    assert chunks[0].section == "POLÍTICA DE RETORNO"
    assert chunks[0].page == 1
    assert chunks[0].parent_id
    assert len(chunks[0].content_hash) == 64
    assert any(chunk.page == 2 and chunk.section == "EXAMES" for chunk in chunks)


def test_route_and_tool_contracts_are_strict():
    with pytest.raises(ValidationError):
        RouteDecision.model_validate(
            {
                "domain": Domain.KNOWLEDGE,
                "action": Action.SEARCH,
                "topic": Topic.RETURN_POLICY,
                "confidence": 0.9,
                "invented": True,
            }
        )
    with pytest.raises(ValidationError):
        validate_tool_arguments("search_knowledge", {"query": "retorno", "token": "secret"})


def test_nullable_provider_strings_are_normalized():
    route = RouteDecision.model_validate(
        {
            "domain": "knowledge",
            "action": "search",
            "topic": "return_policy",
            "confidence": 0.9,
            "unsupported_reason": "none",
        }
    )
    assert route.unsupported_reason is None
