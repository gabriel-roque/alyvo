---
slug: /decisions/0007-scalar-api-reference
---

# ADR 0007 — Scalar como referência interativa

- Status: Accepted
- Data: 2026-11-05

## Contexto

Era necessário um explorador coerente com o contrato e controlável por ambiente.

## Decisão

Servir Scalar em `/docs` e OpenAPI em `/openapi.json`; Swagger/ReDoc ficam desabilitados. `API_DOCS_ENABLED` é falso por padrão em produção e qualquer liberação exige proteção no proxy.

## Alternativas

Swagger/ReDoc duplicariam referências; documentação externa poderia divergir do runtime.

## Consequências

Experiência única, tematizada e testável. Exemplos devem ser sintéticos e nunca conter segredos.

## Links

[Componentes do frontend](../architecture/frontend-components.md).
