"""Reusable maintainability checks shared by CI and regression tests."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Budgets:
    max_file_lines: int = 400
    max_function_lines: int = 60
    max_complexity: int = 15
    legacy_references: tuple[str, ...] = (
        "app.ai",
        "app.routers",
        "app.models",
        "app.db",
        "GenericRepository",
    )


@dataclass(frozen=True)
class Violation:
    path: Path
    code: str
    message: str
    line: int | None = None

    def render(self) -> str:
        location = f"{self.path}:{self.line}" if self.line else str(self.path)
        return f"{location}: {self.message} [{self.code}]"


def inspect_roots(roots: tuple[Path, ...], budgets: Budgets | None = None) -> list[Violation]:
    active = budgets or Budgets()
    return [
        violation
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
        for violation in inspect_source(path, path.read_text(), active)
    ]


def inspect_source(path: Path, source: str, budgets: Budgets | None = None) -> list[Violation]:
    active = budgets or Budgets()
    violations = _file_violations(path, source, active)
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_function_violations(path, node, active))
    return violations


def _file_violations(path: Path, source: str, budgets: Budgets) -> list[Violation]:
    violations: list[Violation] = []
    line_count = len(source.splitlines())
    if line_count > budgets.max_file_lines:
        violations.append(Violation(path, "file-length", f"arquivo com {line_count} linhas"))
    for reference in budgets.legacy_references:
        if reference in source:
            violations.append(
                Violation(path, "legacy-reference", f"referência legada: {reference}")
            )
    return violations


def _function_violations(
    path: Path,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    budgets: Budgets,
) -> list[Violation]:
    violations: list[Violation] = []
    length = (node.end_lineno or node.lineno) - node.lineno + 1
    if length > budgets.max_function_lines:
        violations.append(
            Violation(
                path,
                "function-length",
                f"função {node.name} com {length} linhas",
                node.lineno,
            )
        )
    complexity = _approximate_complexity(node)
    if complexity > budgets.max_complexity:
        violations.append(
            Violation(
                path,
                "complexity",
                f"função {node.name} com complexidade aproximada {complexity}",
                node.lineno,
            )
        )
    return violations


def _approximate_complexity(node: ast.AST) -> int:
    branches = sum(
        isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match))
        + (len(child.values) - 1 if isinstance(child, ast.BoolOp) else 0)
        for child in ast.walk(node)
    )
    return branches + 1
