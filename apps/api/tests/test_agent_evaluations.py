import json
from pathlib import Path

from app.agent.routing import RuleChain

DATASET = Path(__file__).parent / "evals" / "routing.jsonl"


def test_routing_evaluation_dataset():
    chain = RuleChain()
    cases = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]

    failures = []
    for case in cases:
        decision = chain.classify(case["message"])
        actual = {
            "domain": decision.domain,
            "action": decision.action,
            "topic": decision.topic,
        }
        expected = {key: case[key] for key in actual}
        if actual != expected:
            failures.append({"message": case["message"], "expected": expected, "actual": actual})

    assert not failures, failures
