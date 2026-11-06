"""Enforce repository-level maintainability budgets on handwritten Python."""

from __future__ import annotations

import ast
from pathlib import Path

ROOTS = (Path("apps/api/app"), Path("apps/worker/worker"))
LEGACY_IMPORTS = ("app.ai", "app.routers", "app.models", "app.db", "GenericRepository")
failures: list[str] = []

for root in ROOTS:
    for path in root.rglob("*.py"):
        source = path.read_text()
        lines = source.splitlines()
        if len(lines) > 400:
            failures.append(f"{path}: arquivo com {len(lines)} linhas")
        if any(value in source for value in LEGACY_IMPORTS):
            failures.append(f"{path}: referência legada")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if length > 60:
                    failures.append(f"{path}:{node.lineno}: função com {length} linhas")
                branches = sum(
                    isinstance(
                        child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)
                    )
                    + (len(child.values) - 1 if isinstance(child, (ast.BoolOp,)) else 0)
                    for child in ast.walk(node)
                )
                if branches + 1 > 15:
                    failures.append(f"{path}:{node.lineno}: complexidade aproximada {branches + 1}")

if failures:
    raise SystemExit("\n".join(failures))
