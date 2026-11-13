from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

DATASET = Path(__file__).parent / "evals" / "conversation_scenarios.jsonl"


def _cases() -> list[dict[str, object]]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def _normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(character for character in text if not unicodedata.combining(character))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["id"]))
def test_conversation_regression_scenarios_through_public_api(client, case):
    session_id = client.post("/api/v1/chat/sessions").json()["id"]
    response = None
    for turn in case["turns"]:
        response = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            json={"content": turn},
        )
        assert response.status_code == 200, case["id"]

    assert response is not None
    payload = response.json()
    assert payload["intent"] == case["expected_intent"], case["id"]
    assert payload["tool_result"]["type"] == case["expected_result_type"], case["id"]

    evidence = _normalized(
        " ".join(
            (
                payload["answer"],
                json.dumps(payload["tool_result"], ensure_ascii=False),
                json.dumps(payload["citations"], ensure_ascii=False),
            )
        )
    )
    for fact in case["expected_facts"]:
        assert _normalized(fact) in evidence, (case["id"], fact, payload)
    for forbidden in case["forbidden_facts"]:
        assert _normalized(forbidden) not in _normalized(payload["answer"]), (
            case["id"],
            forbidden,
            payload,
        )


def test_regression_dataset_has_unique_ids_and_critical_cases():
    cases = _cases()
    assert len(cases) >= 5
    assert len({case["id"] for case in cases}) == len(cases)
    assert all(case["critical"] for case in cases)
