from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.agent.routing import deterministic_classification

ROOT = Path(__file__).resolve().parents[4]
DATASET = ROOT / "datasets" / "regression" / "semantic-families.jsonl"
MULTIHOP_DATASET = ROOT / "datasets" / "regression" / "multihop.jsonl"


def cases() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


@pytest.mark.parametrize(
    "case",
    [item for item in cases() if not item["history"]],
    ids=lambda item: item["id"],
)
def test_known_semantic_family_has_stable_route(case: dict):
    route = deterministic_classification(case["question"])
    assert route is not None
    expected = case["expected_route"]
    assert route.domain.value == expected["domain"]
    assert route.action.value == expected["action"]
    assert route.topic.value == expected["topic"]


def test_dataset_contract_is_complete_and_ids_are_unique():
    loaded = cases()
    assert len(loaded) >= 20
    assert len({item["id"] for item in loaded}) == len(loaded)
    required = {
        "id",
        "family",
        "question",
        "history",
        "expected_route",
        "expected_tool",
        "expected_facts",
        "forbidden_facts",
        "expected_sources",
        "answerable",
        "criticality",
        "provider_tags",
    }
    assert all(set(item) == required for item in loaded)


def test_multihop_gate_has_twenty_traceable_cases():
    loaded = [
        json.loads(line) for line in MULTIHOP_DATASET.read_text().splitlines() if line.strip()
    ]
    assert len(loaded) >= 20
    assert len({item["id"] for item in loaded}) == len(loaded)
    required = {
        "id",
        "family",
        "question",
        "expected_facts",
        "forbidden_facts",
        "expected_sources",
        "criticality",
    }
    assert all(set(item) == required for item in loaded)
    assert all(item["expected_facts"] for item in loaded)
    assert all(item["expected_sources"] for item in loaded)


def test_critical_paraphrases_reach_the_same_public_tool(client):
    for question in (
        "Qual é a política de retorno das consultas?",
        "E qual é o prazo para o retorno das consultas?",
        "Qual a data limite para retorno de consulta?",
        "Qual o prazo de retorno da consulta particular?",
        "Quando o hemograma fica pronto?",
        "Qual o prazo do resultado do exame de sangue?",
    ):
        session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
        response = client.post(
            f"/api/v1/chat/sessions/{session}/messages",
            json={"content": question},
        )
        assert response.status_code == 200
        assert response.json()["intent"] == "search_knowledge"


def test_return_policy_follow_up_keeps_context(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    first = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Qual é o prazo de retorno pelo convênio?"},
    )
    follow_up = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "E para particular?"},
    )
    assert first.json()["intent"] == "search_knowledge"
    assert follow_up.json()["intent"] == "search_knowledge"


def test_exam_interpretation_is_not_misrouted_to_release_time(client):
    session = client.post("/api/v1/chat/sessions", json={}).json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session}/messages",
        json={"content": "Interprete meu resultado de exame"},
    )
    assert response.json()["intent"] == "clinical_safety"
