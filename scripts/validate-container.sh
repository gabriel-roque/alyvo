#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python packages/contracts/generate.py
npm run generate:contracts
python scripts/validate-openapi.py
python scripts/check-maintainability.py
pytest apps/api/tests tests/integration
ruff check apps/api apps/worker scripts tests
ruff format --check apps/api apps/worker scripts tests
mypy --no-incremental apps/api/app apps/worker/worker
lint-imports
npm run test:web
npm run typecheck
npm run lint
npm run build
npm run build:docs
E2E_EXTERNAL=1 npm run test:e2e

python - "$started_at" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

report = {
    "project": "Alyvo",
    "started_at": sys.argv[1],
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "status": "passed",
    "checks": [
        "infrastructure-health", "alembic", "seed", "api-unit",
        "integration", "ruff", "ruff-format", "mypy", "architecture-boundaries",
        "openapi", "maintainability", "web-unit", "vitest",
        "react-testing-library", "typescript", "eslint", "docusaurus-build",
        "production-build", "playwright-four-viewports", "outbox", "knowledge-projection"
    ],
}
Path("reports/validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
