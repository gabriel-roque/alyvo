---
slug: /decisions/0004-langgraph-boundary
---

# ADR 0004 — Fronteira do LangGraph

- Status: Accepted
- Data: 2026-11-05

## Contexto

Orquestração anterior conhecia persistência, HTTP e compatibilidade de intents.

## Decisão

Restringir o grafo a normalize → classify → plan → execute → validate → present. Tools tipadas chamam casos de uso pelo registry; identidade fica no runtime context.

## Alternativas

Nós autônomos com acesso à infraestrutura reduzem código inicial, mas impedem testes e controle de risco.

## Consequências

Studio usa fixtures sintéticas e o registry centraliza risco/confirmacão; novos fluxos exigem ports explícitos.

## Links

[Agente](../architecture/agent-components.md).
