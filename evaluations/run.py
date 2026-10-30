from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
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


async def ragas_similarity(reference: str, response: str) -> float:
    """Use Ragas' deterministic metric without an external judge model."""
    try:
        from ragas.metrics.collections import DistanceMeasure, NonLLMStringSimilarity

        result = await NonLLMStringSimilarity(
            distance_measure=DistanceMeasure.LEVENSHTEIN
        ).ascore(reference=reference, response=response)
        return float(result.value)
    except ImportError:
        from ragas.dataset_schema import SingleTurnSample
        from ragas.metrics._string import NonLLMStringSimilarity

        sample = SingleTurnSample(reference=reference, response=response)
        return float(await NonLLMStringSimilarity().single_turn_ascore(sample))


async def ragas_term_coverage(expected: list[str], evidence: str) -> float:
    """Fuzzy expected-term coverage scored by Ragas without a remote judge."""
    words = evidence.split()
    scores = []
    for term in expected:
        if normalized(term) in normalized(evidence):
            scores.append(await ragas_similarity(term, term))
            continue
        size = max(len(term.split()), 1)
        candidates = [" ".join(words[index : index + size]) for index in range(max(len(words) - size + 1, 1))]
        scores.append(max([await ragas_similarity(term, candidate) for candidate in candidates] or [0.0]))
    return sum(scores) / len(scores)


def post(
    client: httpx.Client, path: str, payload: dict, headers: dict | None = None
) -> dict:
    response = client.post(f"{API}{path}", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def evaluate_rag(client: httpx.Client) -> dict:
    cases = json.loads((ROOT / "datasets/rag-evaluation.json").read_text())
    route_hits = 0
    recall_scores: list[float] = []
    grounded: list[float] = []
    citation_scores: list[float] = []
    ragas_scores: list[float] = []
    details = []
    for case in cases:
        session = post(client, "/chat/sessions", {"tenant_id": "clinic-alyvo"})["id"]
        result = post(
            client,
            f"/chat/sessions/{session}/messages",
            {"content": case["question"]},
        )
        route_hits += int(result["intent"] == case["intent"])
        evidence = " ".join(
            [result["answer"], *[item.get("excerpt", "") for item in result["citations"]]]
        )
        expected = case["expected_terms"]
        present = [term for term in expected if normalized(term) in normalized(evidence)]
        recall = len(present) / len(expected)
        recall_scores.append(recall)
        is_low_confidence = result["confidence"] < 0.6
        citation_evidence = " ".join(item.get("excerpt", "") for item in result["citations"])
        supported = bool(result["citations"]) and bool(present) and any(normalized(term) in normalized(citation_evidence) for term in present)
        grounded.append(float(supported or is_low_confidence or result["intent"] != "knowledge"))
        citation_scores.append(
            float(all(item.get("title") and item.get("source") and item.get("excerpt") for item in result["citations"]))
        )
        ragas_scores.append(asyncio.run(ragas_term_coverage(expected, evidence)))
        details.append(
            {
                "question": case["question"],
                "intent": result["intent"],
                "recall": recall,
                "confidence": result["confidence"],
            }
        )
    metrics = {
        "intent_accuracy": route_hits / len(cases),
        "recall_at_5": sum(recall_scores) / len(recall_scores),
        "grounded_rate": sum(grounded) / len(grounded),
        "citation_precision": sum(citation_scores) / len(citation_scores),
        "ragas_term_coverage": sum(ragas_scores) / len(ragas_scores),
    }
    return {"metrics": metrics, "details": details}


def patient_headers(client: httpx.Client) -> dict:
    post(
        client,
        "/auth/patient/start",
        {"tenant_id": "clinic-alyvo", "cpf": "123.456.789-09"},
    )
    auth = post(
        client,
        "/auth/patient/verify",
        {"tenant_id": "clinic-alyvo", "cpf": "123.456.789-09", "code": "123456"},
    )
    return {
        "Authorization": f"Bearer {auth['access_token']}",
        "X-Tenant-ID": "clinic-alyvo",
    }


def upload_and_score(
    client: httpx.Client,
    headers: dict,
    filename: str,
    kind: str,
    expected: list[str],
) -> float:
    path = ROOT / "datasets/synthetic-documents" / filename
    with path.open("rb") as stream:
        response = client.post(
            f"{API}/patient/documents",
            headers=headers,
            data={"kind": kind},
            files={"file": (path.name, stream, "image/png")},
        )
    response.raise_for_status()
    item = response.json()
    for _ in range(240):
        if item["status"] not in {"uploaded", "processing"}:
            break
        time.sleep(1)
        poll = client.get(f"{API}/patient/documents/{item['id']}", headers=headers)
        poll.raise_for_status()
        item = poll.json()
    if item["status"] != "review_required":
        return 0.0
    values = " ".join(str(value) for value in item["fields"].values())
    return sum(normalized(term) in normalized(values) for term in expected) / len(expected)


def evaluate_ocr(client: httpx.Client) -> dict:
    expected = json.loads((ROOT / "datasets/ocr-expected.json").read_text())
    headers = patient_headers(client)
    kinds = {"identidade": "identity", "carteirinha": "insurance_card", "pedido-medico": "medical_order"}
    variants = ("limpo", "rotacionado", "desfocado", "ruido")
    scores: dict[str, float] = {}
    for document, kind in kinds.items():
        for variant in variants:
            scores[f"ocr_{document}_{variant}"] = upload_and_score(client, headers, f"{document}-{variant}.png", kind, expected[document])
    clean_scores = [score for key, score in scores.items() if key.endswith("_limpo")]
    degraded_scores = [score for key, score in scores.items() if not key.endswith("_limpo")]
    return {"metrics": {**scores, "clean_required_fields": sum(clean_scores) / len(clean_scores), "degraded_required_fields": sum(degraded_scores) / len(degraded_scores)}}


def main() -> None:
    with httpx.Client(timeout=120) as client:
        rag = evaluate_rag(client)
        ocr = evaluate_ocr(client)
    thresholds = {
        "intent_accuracy": 0.95,
        "recall_at_5": 0.85,
        "grounded_rate": 0.90,
        "citation_precision": 0.90,
        "ragas_term_coverage": 0.85,
        "clean_required_fields": 0.90,
        "degraded_required_fields": 0.80,
    }
    combined = {**rag["metrics"], **ocr["metrics"]}
    failures = {
        name: {"actual": combined[name], "minimum": minimum}
        for name, minimum in thresholds.items()
        if combined[name] < minimum
    }
    report = {
        "status": "passed" if not failures else "failed",
        "metrics": combined,
        "thresholds": thresholds,
        "failures": failures,
        "rag_details": rag["details"],
    }
    target = ROOT / "reports/evaluations.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
