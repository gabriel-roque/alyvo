from __future__ import annotations

import concurrent.futures
import json
import os
import statistics
import time
from pathlib import Path

import httpx

API = os.getenv("API_URL", "http://localhost:8000/api/v1")
ROOT = Path(__file__).resolve().parents[1]
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]


def request(question: str) -> dict:
    with httpx.Client(timeout=60, headers={"X-Tenant-ID": "clinic-alyvo"}) as client:
        session = client.post(f"{API}/chat/sessions", json={}).json()["id"]
        started = time.perf_counter()
        response = client.post(f"{API}/chat/sessions/{session}/messages", json={"content": question})
        elapsed = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        return {"duration_ms": round(elapsed, 1), "intent": response.json()["intent"]}


def batch(concurrency: int, question: str) -> dict:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda _: request(question), range(max(5, concurrency * 3))))
    durations = [item["duration_ms"] for item in results]
    return {
        "concurrency": concurrency,
        "count": len(results),
        "mean_ms": round(statistics.mean(durations), 1),
        "p95_ms": percentile(durations, 0.95),
        "intents": sorted({item["intent"] for item in results}),
    }


def ollama_processor() -> dict:
    try:
        models = httpx.get(f"{OLLAMA}/api/ps", timeout=5).json().get("models", [])
        if not models:
            return {"status": "unavailable", "reason": "no loaded models"}
        model = models[0]
        total = int(model.get("size", 0))
        vram = int(model.get("size_vram", 0))
        ratio = round(vram / total, 4) if total else 0
        return {
            "status": "ok",
            "model": model.get("name"),
            "size": total,
            "size_vram": vram,
            "gpu_ratio": ratio,
        }
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}


def main() -> None:
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ollama_ps": ollama_processor(),
        "availability": [batch(level, "Tem horários na sexta-feira?") for level in (1, 2, 5)],
        "knowledge": [batch(level, "Quais documentos devo levar para exames?") for level in (1, 2, 5)],
    }
    target = ROOT / "reports" / "performance.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    processor_ok = report["ollama_ps"].get("gpu_ratio") == 1
    availability_ok = all(item["p95_ms"] <= 1500 for item in report["availability"])
    knowledge_ok = all(item["p95_ms"] <= 8000 for item in report["knowledge"])
    if not (processor_ok and availability_ok and knowledge_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
