from pathlib import Path

from scripts.maintainability import Budgets, inspect_roots, inspect_source

ROOT = Path(__file__).resolve().parents[4]
APPLICATION_ROOTS = (ROOT / "apps/api/app", ROOT / "apps/worker/worker")


def test_repository_respects_maintainability_budgets():
    violations = inspect_roots(APPLICATION_ROOTS)

    assert not violations, "\n".join(violation.render() for violation in violations)


def test_file_length_gate_detects_regression():
    source = "\n".join("value = 1" for _ in range(6))

    violations = inspect_source(Path("oversized.py"), source, Budgets(max_file_lines=5))

    assert {violation.code for violation in violations} == {"file-length"}


def test_function_length_and_complexity_gates_detect_regression():
    source = "def dense(value):\n" + "\n".join(
        f"    if value == {index}:\n        return {index}" for index in range(4)
    )

    violations = inspect_source(
        Path("dense.py"),
        source,
        Budgets(max_function_lines=5, max_complexity=3),
    )

    assert {violation.code for violation in violations} == {
        "complexity",
        "function-length",
    }


def test_legacy_reference_gate_detects_regression():
    violations = inspect_source(Path("legacy.py"), "from app.ai import agent\n")

    assert {violation.code for violation in violations} == {"legacy-reference"}
