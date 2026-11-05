#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 packages/contracts/generate.py
npm run generate:contracts
python3 -m pytest apps/api/tests tests/integration
python3 -m ruff check apps/api apps/worker datasets evaluations tests conftest.py
python3 -m ruff format --check apps/api apps/worker datasets evaluations tests conftest.py
env -u PYTHONPATH python3 -m mypy --no-incremental apps/api/app/agent apps/api/app/api apps/api/app/core apps/api/app/domain apps/api/app/infrastructure apps/api/app/prompts apps/api/app/retrieval apps/api/app/tools
npm run test:web
npm run typecheck
npm run lint
npm run build
python3 scripts/system-validation.py
E2E_EXTERNAL=1 npm run test:e2e
python3 evaluations/run.py

python3 - "$started_at" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

evaluations = json.loads(Path("reports/evaluations.json").read_text())
metrics = evaluations.get("metrics") or {
    "intent_accuracy": evaluations["intent_accuracy"],
    "term_recall": evaluations["term_recall"],
    "date_accuracy": evaluations["date_accuracy"],
}
report = {
    "project": "Alyvo",
    "started_at": sys.argv[1],
    "finished_at": datetime.now(timezone.utc).isoformat(),
    "status": "passed",
    "checks": [
        "infrastructure-health", "migrations-and-rls", "seed", "api-unit",
        "integration", "ruff", "ruff-format", "mypy", "architecture-boundaries",
        "web-unit", "typescript", "eslint",
        "production-build", "system-scenarios", "playwright-four-viewports",
        "rag-graphrag-retrieval", "knowledge-ocr-ingestion"
    ],
    "metrics": metrics,
}
Path("reports/validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
