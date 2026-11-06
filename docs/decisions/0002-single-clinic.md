---
slug: /decisions/0002-single-clinic
---

# ADR 0002 — Produto single-clinic

- Status: Accepted
- Data: 2026-11-05

## Contexto

O produto atende uma única clínica; tenancy, RLS e filtros propagavam complexidade sem valor.

## Decisão

Remover tenants, claims/headers, filtros e propriedades Neo4j. `clinic_profile` singleton guarda nome, timezone e política.

## Alternativas

Tenant fixo e shims manteriam caminhos mortos e risco de isolamento incorreto.

## Consequências

Modelo e API menores. Voltar a multi-clinic exigirá nova arquitetura e ADR, não reativação de código legado.

## Links

[Visão geral da arquitetura](../architecture/overview.md).
