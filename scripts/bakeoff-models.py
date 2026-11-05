from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

import httpx
from app.ai.workflow import SYSTEM_PROMPT, TOOLS

OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
ROOT = Path(__file__).resolve().parents[1]
MODELS = ("qwen3:8b-q4_K_M", "qwen3.5:4b")
CASES = (
    ("Tem horários na sexta-feira?", "search_availability"),
    ("Quero um cardiologista amanhã", "search_availability"),
    ("Quais médicos atendem cardiologia pelo Amil?", "search_directory"),
    ("Onde fica a Unidade Centro?", "search_directory"),
    ("Quais documentos devo levar para exames?", "search_knowledge"),
    ("Qual é a política de estacionamento?", "search_knowledge"),
    ("Quais são minhas consultas?", "list_my_appointments"),
    ("Quero cancelar uma consulta", "list_my_appointments"),
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]


def model_gpu(client: httpx.Client, model: str) -> dict:
    loaded = next(
        (
            item
            for item in client.get("/api/ps").json().get("models", [])
            if item.get("name") == model
        ),
        None,
    )
    if not loaded:
        return {"loaded": False, "gpu_ratio": 0}
    size = int(loaded.get("size", 0))
    size_vram = int(loaded.get("size_vram", 0))
    return {
        "loaded": True,
        "size": size,
        "size_vram": size_vram,
        "gpu_ratio": round(size_vram / size, 4) if size else 0,
    }


def evaluate_model(client: httpx.Client, model: str) -> dict:
    durations = []
    details = []
    for question, expected in CASES:
        started = time.perf_counter()
        response = client.post(
            "/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "keep_alive": "10m",
                "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 160},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                "tools": TOOLS,
            },
        )
        response.raise_for_status()
        payload = response.json()
        duration_ms = (time.perf_counter() - started) * 1000
        durations.append(duration_ms)
        calls = payload.get("message", {}).get("tool_calls", [])
        actual = calls[0].get("function", {}).get("name") if calls else None
        details.append(
            {
                "question": question,
                "expected": expected,
                "actual": actual,
                "match": actual == expected,
                "duration_ms": round(duration_ms, 1),
            }
        )

    naturalness_samples = []
    for question in (
        "Onde fica a Unidade Centro?",
        "Quais documentos devo levar para um exame?",
        "Explique de forma acolhedora que você é uma assistente virtual administrativa.",
    ):
        response = client.post(
            "/api/chat",
            json={
                "model": model,
                "stream": False,
                "think": False,
                "keep_alive": "10m",
                "options": {"temperature": 0.15, "num_ctx": 4096, "num_predict": 128},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Responda em português brasileiro natural, direto e acolhedor, "
                            "em até três frases. Não invente informações."
                        ),
                    },
                    {"role": "user", "content": question},
                ],
            },
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "").strip()
        naturalness_samples.append(
            {
                "question": question,
                "answer": answer,
                "basic_quality": bool(answer) and "<think>" not in answer and len(answer) <= 600,
            }
        )

    return {
        "tool_accuracy": round(sum(item["match"] for item in details) / len(details), 4),
        "mean_ms": round(statistics.mean(durations), 1),
        "p95_ms": round(percentile(durations, 0.95), 1),
        "gpu": model_gpu(client, model),
        "tool_cases": details,
        "naturalness_samples": naturalness_samples,
        "basic_naturalness_pass": all(item["basic_quality"] for item in naturalness_samples),
    }


def main() -> None:
    with httpx.Client(base_url=OLLAMA, timeout=120) as client:
        results = {model: evaluate_model(client, model) for model in MODELS}
    primary = results[MODELS[0]]
    challenger = results[MODELS[1]]
    latency_improvement = 1 - challenger["p95_ms"] / primary["p95_ms"] if primary["p95_ms"] else 0
    # The production model already has a real-patient panel score. The challenger
    # cannot claim the required +0.2 without repeating that independent panel.
    naturalness_delta_verified = False
    challenger_qualified = (
        challenger["tool_accuracy"] >= primary["tool_accuracy"]
        and latency_improvement >= 0.2
        and challenger["gpu"]["gpu_ratio"] == 1
        and naturalness_delta_verified
    )
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "criteria": {
            "same_or_better_tool_accuracy": True,
            "p95_improvement_minimum": 0.2,
            "naturalness_delta_minimum": 0.2,
            "no_cpu_offload": True,
        },
        "models": results,
        "challenger_p95_improvement": round(latency_improvement, 4),
        "naturalness_delta_verified": naturalness_delta_verified,
        "decision": "qwen3.5:4b" if challenger_qualified else "qwen3:8b-q4_K_M",
        "reason": (
            "challenger met every replacement gate"
            if challenger_qualified
            else "challenger did not prove every replacement gate; keep the validated production model"
        ),
    }
    target = ROOT / "reports" / "model-bakeoff.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
