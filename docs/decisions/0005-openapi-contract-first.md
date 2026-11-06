---
slug: /decisions/0005-openapi-contract-first
---

# ADR 0005 — OpenAPI contract-first

- Status: Accepted
- Data: 2026-11-05

## Contexto

Chamadas manuais e casts no frontend permitiam drift de rotas e payloads.

## Decisão

OpenAPI é gerado de schemas estritos e produz o único cliente TypeScript, baseado em `openapi-fetch`. CI falha se artefatos diferirem.

## Alternativas

Tipos duplicados manualmente não garantem correspondência; SDK artesanal repete parsing e autenticação.

## Consequências

Mudanças incompatíveis aparecem no build. SSE permanece documentado no mesmo contrato.

## Links

[Componentes do frontend](../architecture/frontend-components.md).
