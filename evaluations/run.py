from __future__ import annotations

import json
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = os.getenv("API_URL", "http://localhost:8000/api/v1")


def normalized(value: str) -> str:
    unaccented = "".join(
        character
        for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", unaccented).split())


def _legacy_cases() -> list[dict]:
    cases = json.loads((ROOT / "datasets/rag-evaluation.json").read_text())
    return [
        {
            "id": f"legacy-{index:03}",
            "family": item["intent"],
            "question": item["question"],
            "history": [],
            "expected_intent": item["intent"],
            "expected_facts": item["expected_terms"],
            "forbidden_facts": [],
            "expected_sources": [],
            "answerable": item["strategy"] != "low-confidence",
            "criticality": "normal",
            "date_required": item.get("strategy") in {"date", "date-range"},
        }
        for index, item in enumerate(cases, start=1)
    ]


def _regression_cases() -> list[dict]:
    path = ROOT / "datasets/regression/semantic-families.jsonl"
    domain_intents = {
        "clinical_safety": "clinical_safety",
        "security": "security",
    }
    loaded = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        item["expected_intent"] = item["expected_tool"] or domain_intents.get(
            item["expected_route"]["domain"],
            item["expected_route"]["topic"],
        )
        item["date_required"] = False
        loaded.append(item)
    return loaded


def _source_rank(citations: list[dict], expected_sources: list[str]) -> int | None:
    if not expected_sources:
        return None
    expected = [normalized(item) for item in expected_sources]
    for index, citation in enumerate(citations, start=1):
        haystack = normalized(f"{citation.get('title', '')} {citation.get('source', '')}")
        if any(item in haystack or haystack in item for item in expected):
            return index
    return 0


def evaluate(client: httpx.Client) -> dict:
    cases = [*_legacy_cases(), *_regression_cases()]
    details = []
    for case in cases:
        session_response = client.post(
            f"{API}/chat/sessions",
            json={"tenant_id": "clinic-alyvo"},
        )
        session_response.raise_for_status()
        session = session_response.json()["id"]
        for previous in case.get("history", []):
            if previous.get("role") == "user":
                history_response = client.post(
                    f"{API}/chat/sessions/{session}/messages",
                    json={"content": previous["content"]},
                )
                history_response.raise_for_status()
        response = client.post(
            f"{API}/chat/sessions/{session}/messages",
            json={"content": case["question"]},
        )
        response.raise_for_status()
        result = response.json()
        evidence = " ".join(
            [
                result["answer"],
                *[item.get("excerpt", "") for item in result["citations"]],
                json.dumps(result.get("tool_result") or {}, ensure_ascii=False),
            ]
        )
        expected_facts = case["expected_facts"]
        fact_recall = (
            sum(normalized(term) in normalized(evidence) for term in expected_facts)
            / len(expected_facts)
            if expected_facts
            else 1.0
        )
        forbidden_ok = all(
            normalized(term) not in normalized(evidence) for term in case.get("forbidden_facts", [])
        )
        date_resolved = not case["date_required"] or bool(
            (result.get("resolved_request") or {}).get("from")
        )
        source_rank = _source_rank(
            result.get("citations", []),
            case.get("expected_sources", []),
        )
        actual_abstention = not result.get("citations") and not result.get("tool_result")
        details.append(
            {
                "id": case["id"],
                "family": case["family"],
                "criticality": case["criticality"],
                "question": case["question"],
                "expected_intent": case["expected_intent"],
                "actual_intent": result["intent"],
                "intent_match": result["intent"] == case["expected_intent"],
                "fact_recall": fact_recall,
                "forbidden_ok": forbidden_ok,
                "date_resolved": date_resolved,
                "source_rank": source_rank,
                "expected_abstention": not case["answerable"],
                "actual_abstention": actual_abstention,
                "confidence": result["confidence"],
            }
        )

    by_family: dict[str, list[dict]] = defaultdict(list)
    for item in details:
        by_family[item["family"]].append(item)
    family_metrics = {
        family: {
            "route_accuracy": sum(item["intent_match"] for item in items) / len(items),
            "fact_recall": sum(item["fact_recall"] for item in items) / len(items),
        }
        for family, items in sorted(by_family.items())
    }
    ranked = [item for item in details if item["source_rank"] is not None]
    recall_at_5 = (
        sum(0 < item["source_rank"] <= 5 for item in ranked) / len(ranked) if ranked else 1.0
    )
    mrr_at_5 = (
        sum(1 / item["source_rank"] if 0 < item["source_rank"] <= 5 else 0 for item in ranked)
        / len(ranked)
        if ranked
        else 1.0
    )
    true_abstentions = sum(
        item["expected_abstention"] and item["actual_abstention"] for item in details
    )
    predicted_abstentions = sum(item["actual_abstention"] for item in details)
    expected_abstentions = sum(item["expected_abstention"] for item in details)
    return {
        "route_accuracy": sum(item["intent_match"] for item in details) / len(details),
        "fact_recall": sum(item["fact_recall"] for item in details) / len(details),
        "date_accuracy": sum(item["date_resolved"] for item in details) / len(details),
        "recall_at_5": recall_at_5,
        "mrr_at_5": mrr_at_5,
        "abstention_precision": true_abstentions / max(predicted_abstentions, 1),
        "abstention_recall": true_abstentions / max(expected_abstentions, 1),
        "family_metrics": family_metrics,
        "details": details,
    }


def main() -> None:
    with httpx.Client(timeout=120) as client:
        result = evaluate(client)
    critical = [item for item in result["details"] if item["criticality"] == "critical"]
    critical_ok = all(
        item["intent_match"]
        and item["fact_recall"] == 1
        and item["forbidden_ok"]
        and item["date_resolved"]
        for item in critical
    )
    families_ok = all(
        metrics["route_accuracy"] >= 0.95 for metrics in result["family_metrics"].values()
    )
    passed = (
        critical_ok
        and families_ok
        and result["route_accuracy"] >= 0.98
        and result["fact_recall"] >= 0.95
        and result["date_accuracy"] == 1.0
        and result["recall_at_5"] >= 0.95
        and result["mrr_at_5"] >= 0.90
        and result["abstention_precision"] >= 0.95
        and result["abstention_recall"] >= 0.95
        and all(item["forbidden_ok"] for item in result["details"])
    )
    report = {"status": "passed" if passed else "failed", "metrics": result}
    target = ROOT / "reports/evaluations.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
