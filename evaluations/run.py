from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("API_URL", "http://localhost:8000/api/v1")


def normalized(value: str) -> str:
    unaccented = "".join(character for character in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unaccented).split())


def evaluate(client: httpx.Client) -> dict:
    cases = json.loads((ROOT / "datasets/rag-evaluation.json").read_text())
    details = []
    for case in cases:
        session_response = client.post(f"{API}/chat/sessions", json={"tenant_id": "clinic-alyvo"})
        session_response.raise_for_status()
        session = session_response.json()["id"]
        response = client.post(f"{API}/chat/sessions/{session}/messages", json={"content": case["question"]})
        response.raise_for_status()
        result = response.json()
        evidence = " ".join([result["answer"], *[item.get("excerpt", "") for item in result["citations"]]])
        recall = sum(normalized(term) in normalized(evidence) for term in case["expected_terms"]) / len(case["expected_terms"])
        details.append({"question": case["question"], "expected_intent": case["intent"], "actual_intent": result["intent"], "intent_match": result["intent"] == case["intent"], "term_recall": recall, "confidence": result["confidence"]})
    return {
        "intent_accuracy": sum(item["intent_match"] for item in details) / len(details),
        "term_recall": sum(item["term_recall"] for item in details) / len(details),
        "details": details,
    }


def main() -> None:
    with httpx.Client(timeout=120) as client:
        result = evaluate(client)
    passed = result["intent_accuracy"] >= 0.9 and result["term_recall"] >= 0.75
    report = {"status": "passed" if passed else "failed", **result}
    target = ROOT / "reports/evaluations.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
