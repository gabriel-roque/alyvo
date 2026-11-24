from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

DATASET = Path(__file__).parent / "evals" / "rag_scenarios.jsonl"


def _cases() -> list[dict[str, object]]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def _normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(character for character in text if not unicodedata.combining(character))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["id"]))
def test_rag_context_relevance_faithfulness_and_answerability(client, case):
    session_id = client.post("/api/v1/chat/sessions").json()["id"]
    response = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"content": case["question"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "search_knowledge"
    assert payload["tool_result"]["type"] == "knowledge"
    evidence = _normalized(
        " ".join(
            (
                payload["answer"],
                json.dumps(payload["citations"], ensure_ascii=False),
            )
        )
    )
    if case["supported"]:
        assert payload["confidence"] > 0
        assert payload["citations"]
        for fact in case["expected_facts"]:
            assert _normalized(fact) in evidence
    else:
        assert payload["confidence"] == 0
        assert payload["citations"] == []
        assert "não encontrei" in payload["answer"].casefold()


def test_rag_evaluation_dataset_has_supported_and_unanswerable_cases():
    cases = _cases()
    assert len(cases) >= 6
    assert any(case["supported"] for case in cases)
    assert any(not case["supported"] for case in cases)
    assert len({case["id"] for case in cases}) == len(cases)
