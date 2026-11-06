---
slug: /decisions/0006-alembic
---

# ADR 0006 — Alembic como autoridade do schema

- Status: Accepted
- Data: 2026-11-05

## Contexto

`create_all` e runner SQL no startup não forneciam histórico ou rollout controlado.

## Decisão

Usar baseline Alembic para banco vazio e serviço `migrate` anterior a API/worker. Seed é comando explícito.

## Alternativas

DDL no startup mistura lifecycle e schema; scripts SQL avulsos não representam uma cadeia verificável.

## Consequências

Deploy previsível e revisável; cada migration deve atualizar modelo e documentação.

## Links

[Deployment](../architecture/deployment.md).
