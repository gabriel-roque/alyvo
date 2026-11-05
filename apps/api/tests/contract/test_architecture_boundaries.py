from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "apps" / "api" / "app"
WORKER = ROOT / "apps" / "worker" / "worker"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def python_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.py") if "__pycache__" not in path.parts]


def test_domain_has_no_framework_or_infrastructure_dependencies():
    forbidden = ("fastapi", "langchain", "langgraph", "neo4j", "boto3", "app.routers", "app.api")
    violations = {
        str(path.relative_to(ROOT)): sorted(
            name for name in imports(path) if name.startswith(forbidden)
        )
        for path in python_files(APP / "domain")
    }
    assert not {path: names for path, names in violations.items() if names}


def test_new_agent_tool_and_retrieval_layers_do_not_import_routers():
    violations = {}
    for package in ("agent", "tools", "retrieval"):
        for path in python_files(APP / package):
            bad = sorted(name for name in imports(path) if name.startswith("app.routers"))
            if bad:
                violations[str(path.relative_to(ROOT))] = bad
    assert not violations


def test_worker_does_not_import_http_layer():
    violations = {
        str(path.relative_to(ROOT)): sorted(
            name for name in imports(path) if name.startswith(("app.routers", "app.api"))
        )
        for path in python_files(WORKER)
    }
    assert not {path: names for path, names in violations.items() if names}
