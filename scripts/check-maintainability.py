"""Enforce repository-level maintainability budgets on handwritten Python."""

from pathlib import Path

from maintainability import inspect_roots

ROOTS = (Path("apps/api/app"), Path("apps/worker/worker"))
violations = inspect_roots(ROOTS)

if violations:
    raise SystemExit("\n".join(violation.render() for violation in violations))
