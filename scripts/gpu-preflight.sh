#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "GPU preflight: FALHOU — $1" >&2
  exit 1
}

command -v nvidia-smi >/dev/null || fail "driver NVIDIA/nvidia-smi não encontrado"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader || fail "GPU NVIDIA indisponível"
docker info >/dev/null 2>&1 || fail "Docker indisponível para o usuário atual"
docker compose config >/dev/null || fail "docker-compose.yml inválido"

if docker compose ps --status running --services | grep -qx ollama; then
  docker compose exec -T ollama nvidia-smi >/dev/null || fail "O contêiner Ollama não enxerga a GPU; instale/configure o NVIDIA Container Toolkit"
  processor="$(docker compose exec -T ollama ollama ps | tail -n +2)"
  echo "Ollama: ${processor:-modelo ainda não carregado}"
  if docker compose exec -T ollama ollama ps | tail -n +2 | grep -qv '100% GPU'; then
    fail "o modelo não está 100% carregado na GPU"
  fi
fi

echo "GPU preflight: OK"
