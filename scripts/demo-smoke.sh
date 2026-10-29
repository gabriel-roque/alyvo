#!/usr/bin/env bash
set -euo pipefail

api_url="${API_URL:-http://localhost:8000}"
curl --fail --silent "${api_url}/health"
curl --fail --silent "${api_url}/api/v1/meta"
echo
echo "API Alyvo saudável em ${api_url}"

