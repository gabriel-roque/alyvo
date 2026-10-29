#!/usr/bin/env bash
set -euo pipefail

mkdir -p reports
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python_bin="${PYTHON_BIN:-.venv/bin/python}"
pytest_bin="${PYTEST_BIN:-.venv/bin/pytest}"
ruff_bin="${RUFF_BIN:-.venv/bin/ruff}"

"${pytest_bin}" apps/api/tests tests/integration
"${ruff_bin}" check apps/api apps/worker datasets tests conftest.py
npm run test:web
npm run typecheck
npm run lint
npm run build
npm run test:e2e
docker compose -f infra/docker-compose.yml config --quiet
PYTHONPATH=apps/api "${python_bin}" packages/contracts/generate.py

if [[ "${VALIDATE_WITH_INFRA:-0}" == "1" ]]; then
  docker compose -f infra/docker-compose.yml up -d postgres redis neo4j minio mailpit
  docker compose -f infra/docker-compose.yml ps
fi

cat > reports/validation.json <<JSON
{
  "project": "Alyvo",
  "started_at": "${started_at}",
  "finished_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "passed",
  "checks": ["api-tests", "integration-tests", "ruff", "web-tests", "typescript", "eslint", "next-build", "playwright-e2e", "compose-config", "openapi"]
}
JSON

echo "Validação concluída: reports/validation.json"

